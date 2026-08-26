from __future__ import annotations

"""Production-V2 engine boundary.

Temporary architecture mode:
- all 1A-8G sub-engines are PAUSED;
- E1 is a fully independent market-state brain;
- engines do not consume peer-engine evidence;
- E9 remains the only trade-decision authority.
"""

from typing import Any
from .contracts import EngineResult
from .e1_brain import analyze_e1

ENGINE_NAMES = {
    "E1": "Market State Brain", "E2": "Opportunity / Regime Brain", "E3": "Market Structure Brain",
    "E4": "Liquidity Brain", "E5": "Location / Value Brain", "E6": "Setup Brain",
    "E7": "Confirmation Brain", "E8": "Trade Economics Brain", "E9": "Master Decision Brain",
}
ENGINE_IDS = ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8")
SUB_ENGINE_CODES = {
    "E1": ("1A", "1B", "1C", "1D", "1E", "1F", "1G"), "E2": ("2A", "2B", "2C", "2D", "2E", "2F"),
    "E3": ("3A", "3B", "3C", "3D", "3E", "3F"), "E4": ("4A", "4B", "4C", "4D", "4E", "4F"),
    "E5": ("5A", "5B", "5C", "5D", "5E", "5F"), "E6": ("6A", "6B", "6C", "6D", "6E", "6F"),
    "E7": ("7A", "7B", "7C", "7D", "7E", "7F"), "E8": ("8A", "8B", "8C", "8D", "8E", "8F", "8G"),
}
SUB_ENGINES_ENABLED = False
EVIDENCE_INPUTS = {engine_id: tuple() for engine_id in ENGINE_IDS}


def _paused_engine(engine_id: str) -> EngineResult:
    output = {
        "architecture": "ENGINE_INDEPENDENT_SUB_ENGINES_PAUSED", "engine_id": engine_id,
        "analysis_status": "PAUSED_SUB_ENGINES", "sub_engines_enabled": False,
        "sub_engines": list(SUB_ENGINE_CODES[engine_id]), "specialists": {}, "peer_evidence_count": 0,
        "peer_evidence_used": False, "upstream_decisions_used": False, "upstream_gates_used": False,
        "score_used": False, "decision": None, "gate": None, "trade_decision_authority": False,
        "decision_authority": "E9_ONLY", "reasoning_role": "ENGINE_INDEPENDENT_ANALYST_PAUSED",
        "professional_reasoning": {"status": "SUB_ENGINES_PAUSED", "question": {
            "E2": "What opportunity is being offered?", "E3": "What is price structure communicating?",
            "E4": "Where is liquidity and what did price do with it?", "E5": "Is current location advantageous?",
            "E6": "What setup is forming?", "E7": "Has the thesis been confirmed?", "E8": "Is the trade economically attractive?",
        }.get(engine_id, "Engine analysis paused")},
    }
    return EngineResult(engine_id, ENGINE_NAMES[engine_id], None, 0.0, output, ("SUB_ENGINES_PAUSED",))


def _normalize_e1(brain: dict[str, Any]) -> dict[str, Any]:
    out = dict(brain)
    pressure = str(out.get("directional_pressure") or "NEUTRAL").upper()
    if pressure == "UP":
        label = "BULLISH"
    elif pressure == "DOWN":
        label = "BEARISH"
    else:
        label = "NEUTRAL"
    out["directional_pressure"] = label
    reasoning = dict(out.get("professional_reasoning") or {})
    reasoning["directional_pressure"] = label
    reasoning["market_state"] = out.get("market_state")
    reasoning["confidence"] = out.get("confidence")
    out["professional_reasoning"] = reasoning
    return out


def run_engine(engine_id: str, snapshot: dict[str, Any], evidence_bus: dict[str, Any] | None = None) -> EngineResult:
    """Run one engine with a strict independent boundary.

    `evidence_bus` is deliberately ignored. No engine can influence another
    engine while the sub-engine isolation phase is active.
    """
    if engine_id not in ENGINE_IDS:
        raise ValueError(f"unknown_engine={engine_id}")
    if engine_id == "E1":
        brain = _normalize_e1(analyze_e1(snapshot.get("bars") or []))
        output = {
            "architecture": "E1_INDEPENDENT_PROFESSIONAL_BRAIN_V3", "sub_engines_enabled": False,
            "specialists": {}, "peer_evidence_count": 0, "peer_evidence_used": False,
            "upstream_decisions_used": False, "upstream_gates_used": False, "score_used": False,
            "reasoning_role": "MARKET_STATE_ANALYST", **brain,
        }
        return EngineResult("E1", ENGINE_NAMES["E1"], None, float(brain.get("confidence", 0.0)) * 100.0, output, ())
    return _paused_engine(engine_id)


def run_all_parallel(snapshot: dict[str, Any]) -> list[EngineResult]:
    return [run_engine(engine_id, snapshot, None) for engine_id in ENGINE_IDS]
