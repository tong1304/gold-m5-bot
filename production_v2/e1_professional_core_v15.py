"""E1 V15 — structure-first reconciliation layer over the V14/V12 core.

V15 fixes one professional-arbitration defect: a strong, persistent current
structure may not be overridden by long-horizon/EMA context alone. The conflict
is preserved as counter-evidence and remains a WATCH until structural repricing
confirms a true regime transition.
"""
from __future__ import annotations

from typing import Any

from .e1_professional_core_v14 import analyze_e1_professional_v14

DIRECTIONS = {"UP", "DOWN"}


def select_dominant_direction_v15(
    *,
    structure_direction: str,
    structure_quality: float,
    structural_persistence: bool,
    long_direction: str,
    long_consensus: float,
    long_persistence: float,
    ema_relation: str,
    ema_gap: float,
) -> dict[str, Any]:
    """Select E1's dominant market-state direction using strict structure-first rules.

    A strong/persistent current structure wins over a conflicting long-horizon
    direction when the latter is supported only by EMA/context. The conflict is
    explicitly returned so downstream engines can treat it as counter-evidence.
    """
    sd = str(structure_direction or "NEUTRAL").upper()
    ld = str(long_direction or "NEUTRAL").upper()
    ema = str(ema_relation or "NEUTRAL").upper()
    strong_structure = sd in DIRECTIONS and float(structure_quality) >= 0.62
    persistent_long = ld in DIRECTIONS and float(long_consensus) >= (2.0 / 3.0) and float(long_persistence) >= (2.0 / 3.0)
    opposite_horizon = strong_structure and persistent_long and sd != ld

    if opposite_horizon and bool(structural_persistence):
        return {
            "direction": sd,
            "basis": "STRUCTURE_FIRST_COUNTER_HORIZON",
            "blocked_override": True,
            "counter_horizon_direction": ld,
            "ema_context": ema,
            "ema_gap": float(ema_gap),
        }

    if persistent_long and ema == ld and abs(float(ema_gap)) >= 0.50:
        return {
            "direction": ld,
            "basis": "LONG_HORIZON_EMA_ALIGNMENT",
            "blocked_override": False,
            "counter_horizon_direction": sd if sd in DIRECTIONS and sd != ld else "NEUTRAL",
            "ema_context": ema,
            "ema_gap": float(ema_gap),
        }

    if strong_structure and sd == ema:
        return {
            "direction": sd,
            "basis": "STRUCTURE_EMA_ALIGNMENT",
            "blocked_override": False,
            "counter_horizon_direction": ld if ld in DIRECTIONS and ld != sd else "NEUTRAL",
            "ema_context": ema,
            "ema_gap": float(ema_gap),
        }

    return {
        "direction": "NEUTRAL",
        "basis": "NO_DOMINANT_REGIME",
        "blocked_override": False,
        "counter_horizon_direction": ld if ld in DIRECTIONS else "NEUTRAL",
        "ema_context": ema,
        "ema_gap": float(ema_gap),
    }


def analyze_e1_professional_v15(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    result = analyze_e1_professional_v14(bars)
    if result.get("analysis_status") != "COMPLETE":
        return result

    structure = str(result.get("structure_state") or "MIXED").upper()
    structure_direction = "UP" if structure == "BULLISH" else "DOWN" if structure == "BEARISH" else "NEUTRAL"
    quality = float(result.get("structure_quality") or 0.0)
    persistence = bool(result.get("structural_persistence"))
    pr = result.get("professional_reasoning") or {}
    independent = result.get("independent_evidence") or {}
    pressure = independent.get("pressure") or {}
    long_direction = str((result.get("directional_consensus") or {}).get("direction") or "NEUTRAL").upper()
    long_consensus = float((result.get("directional_consensus") or {}).get("long_horizon_score") or 0.0)
    long_persistence = float((independent.get("persistence") or {}).get("long_horizon_score") or 0.0)
    ema_ctx = independent.get("ema_context") or {}
    ema_relation = str(ema_ctx.get("relation") or "NEUTRAL").upper()
    ema_gap = float(ema_ctx.get("gap_atr") or 0.0)

    selected = select_dominant_direction_v15(
        structure_direction=structure_direction,
        structure_quality=quality,
        structural_persistence=persistence,
        long_direction=long_direction,
        long_consensus=long_consensus,
        long_persistence=long_persistence,
        ema_relation=ema_relation,
        ema_gap=ema_gap,
    )
    if not selected["blocked_override"]:
        result["e1_contract_version"] = "PROFESSIONAL_MARKET_STATE_V15"
        result["e1_engine_version"] = "PROFESSIONAL_MARKET_STATE_V15"
        result["architecture"] = "E1_SINGLE_PROFESSIONAL_BRAIN_V15"
        return result

    direction = selected["direction"]
    state = "TREND_UP" if direction == "UP" else "TREND_DOWN"
    result["architecture"] = "E1_SINGLE_PROFESSIONAL_BRAIN_V15"
    result["market_state"] = state
    result["trend_state"] = direction
    result["dominant_direction"] = direction
    result["directional_pressure"] = pressure.get("direction", result.get("directional_pressure"))
    result["structure_alignment"] = "ALIGNED"
    result["directional_state"] = "DEVELOPING"
    result["transition"] = "WATCH"
    result["transition_status"] = "WATCH"
    result["transition_confirmed"] = False
    result["transition_committed"] = False
    result["confidence"] = min(float(result.get("confidence") or 0.0), 0.82)
    result["conflicts"] = list(dict.fromkeys([*(result.get("conflicts") or []), "LONG_HORIZON_VS_CURRENT_STRUCTURE"]))
    result["reasons"] = list(dict.fromkeys([
        *(result.get("reasons") or []),
        "V15_STRUCTURE_FIRST_COUNTER_HORIZON",
        "V15_LONG_HORIZON_IS_CONTEXT_NOT_STATE_OVERRIDE",
        "V15_TRANSITION_REQUIRES_STRUCTURAL_REPRICING",
    ]))
    result["observations"] = [
        *(result.get("observations") or []),
        f"v15_selected_direction={direction}",
        "v15_blocked_long_horizon_override=True",
        f"v15_counter_horizon={selected['counter_horizon_direction']}",
    ]
    result["evidence"] = result["observations"]
    result["professional_reasoning"] = {
        **pr,
        "direction": direction,
        "directional_state": "DEVELOPING",
        "dominant_basis": selected["basis"],
        "structure_first": True,
        "counter_horizon_direction": selected["counter_horizon_direction"],
        "long_horizon_is_context_not_state_override": True,
        "transition_requires": "PERSISTENT_STRUCTURAL_REPRICING",
    }
    result["e1_contract_version"] = "PROFESSIONAL_MARKET_STATE_V15"
    result["e1_engine_version"] = "PROFESSIONAL_MARKET_STATE_V15"
    result["e1_trade_authority"] = False
    return result


__all__ = ["analyze_e1_professional_v15", "select_dominant_direction_v15"]
