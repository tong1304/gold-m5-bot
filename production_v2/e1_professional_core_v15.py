"""E1 V16 — professional market-state arbitration.

V16 keeps E1 strictly inside market-state analysis and fixes a critical
arbitration defect: long-horizon/EMA context may describe background context,
but it cannot promote a mixed/weak current structure into a TREND state.
Current structural evidence is authoritative for the M5 state; conflicting
horizon evidence is preserved as counter-evidence and remains WATCH until
persistent structural repricing is actually confirmed.
"""
from __future__ import annotations

from typing import Any

from .e1_professional_core_v14 import analyze_e1_professional_v14

DIRECTIONS = {"UP", "DOWN"}
MIN_STRONG_STRUCTURE_QUALITY = 0.62
MIN_USABLE_STRUCTURE_QUALITY = 0.52
MIN_PERSISTENCE = 2.0 / 3.0


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
    """Select the current M5 market-state direction.

    Professional arbitration rules:
    1. Strong, persistent current structure has first authority.
    2. A mixed/weak current structure cannot be promoted to a trend by
       long-horizon persistence or EMA alignment alone.
    3. Long-horizon and EMA evidence are context, not substitutes for current
       structural confirmation.
    4. A strong current structure opposite the horizon remains the state while
       the conflict is explicitly preserved for transition monitoring.
    """
    sd = str(structure_direction or "NEUTRAL").upper()
    ld = str(long_direction or "NEUTRAL").upper()
    ema = str(ema_relation or "NEUTRAL").upper()
    quality = float(structure_quality or 0.0)
    gap = float(ema_gap or 0.0)
    long_cons = float(long_consensus or 0.0)
    long_persist = float(long_persistence or 0.0)

    strong_structure = sd in DIRECTIONS and quality >= MIN_STRONG_STRUCTURE_QUALITY
    usable_structure = sd in DIRECTIONS and quality >= MIN_USABLE_STRUCTURE_QUALITY
    persistent_long = (
        ld in DIRECTIONS
        and long_cons >= MIN_PERSISTENCE
        and long_persist >= MIN_PERSISTENCE
    )
    persistent_structure = strong_structure and bool(structural_persistence)
    opposite_horizon = strong_structure and persistent_long and sd != ld

    # Rule 1: persistent current structure is the state authority.
    if persistent_structure:
        return {
            "direction": sd,
            "basis": "PERSISTENT_CURRENT_STRUCTURE",
            "blocked_override": bool(opposite_horizon),
            "counter_horizon_direction": ld if ld in DIRECTIONS and ld != sd else "NEUTRAL",
            "ema_context": ema,
            "ema_gap": gap,
        }

    # Rule 2: strong current structure still outranks a conflicting horizon.
    if opposite_horizon:
        return {
            "direction": sd,
            "basis": "STRUCTURE_FIRST_COUNTER_HORIZON",
            "blocked_override": True,
            "counter_horizon_direction": ld,
            "ema_context": ema,
            "ema_gap": gap,
        }

    # Rule 3: horizon/EMA can support a current structural direction, but
    # cannot create one when current structure is mixed/weak/neutral.
    if usable_structure and persistent_long and sd == ld and ema == ld and abs(gap) >= 0.50:
        return {
            "direction": sd,
            "basis": "CURRENT_STRUCTURE_WITH_HORIZON_EMA_SUPPORT",
            "blocked_override": False,
            "counter_horizon_direction": "NEUTRAL",
            "ema_context": ema,
            "ema_gap": gap,
        }

    # Rule 4: strong structure + EMA agreement can establish a developing
    # current state even before full long-horizon persistence exists.
    if strong_structure and sd == ema and abs(gap) >= 0.50:
        return {
            "direction": sd,
            "basis": "STRUCTURE_EMA_ALIGNMENT",
            "blocked_override": False,
            "counter_horizon_direction": ld if ld in DIRECTIONS and ld != sd else "NEUTRAL",
            "ema_context": ema,
            "ema_gap": gap,
        }

    # Critical guard: no current structural authority = no dominant trend.
    return {
        "direction": "NEUTRAL",
        "basis": "NO_DOMINANT_REGIME",
        "blocked_override": False,
        "counter_horizon_direction": ld if ld in DIRECTIONS else "NEUTRAL",
        "ema_context": ema,
        "ema_gap": gap,
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

    result["e1_contract_version"] = "PROFESSIONAL_MARKET_STATE_V16"
    result["e1_engine_version"] = "PROFESSIONAL_MARKET_STATE_V16"
    result["architecture"] = "E1_SINGLE_PROFESSIONAL_BRAIN_V16"
    result["professional_reasoning"] = {
        **pr,
        "structure_first": True,
        "dominant_basis": selected["basis"],
        "counter_horizon_direction": selected["counter_horizon_direction"],
        "long_horizon_is_context_not_state_override": True,
        "transition_requires": "PERSISTENT_STRUCTURAL_REPRICING",
    }

    if selected["direction"] in DIRECTIONS:
        direction = selected["direction"]
        result["market_state"] = "TREND_UP" if direction == "UP" else "TREND_DOWN"
        result["trend_state"] = direction
        result["dominant_direction"] = direction
        result["directional_pressure"] = pressure.get("direction", result.get("directional_pressure"))
        result["structure_alignment"] = "ALIGNED"
        result["transition"] = "WATCH" if selected["blocked_override"] else result.get("transition", "ABSENT")
        result["transition_status"] = "WATCH" if selected["blocked_override"] else result.get("transition_status", "ABSENT")
        result["transition_confirmed"] = False
        result["transition_committed"] = False
        result["professional_reasoning"] = {
            **result["professional_reasoning"],
            "direction": direction,
            "directional_state": result.get("directional_state", "DEVELOPING"),
            "counter_horizon_direction": selected["counter_horizon_direction"],
        }
        if selected["blocked_override"]:
            result["conflicts"] = list(dict.fromkeys([
                *(result.get("conflicts") or []),
                "LONG_HORIZON_VS_CURRENT_STRUCTURE",
            ]))
            result["reasons"] = list(dict.fromkeys([
                *(result.get("reasons") or []),
                "V16_STRUCTURE_FIRST_COUNTER_HORIZON",
                "V16_LONG_HORIZON_IS_CONTEXT_NOT_STATE_OVERRIDE",
                "V16_TRANSITION_REQUIRES_STRUCTURAL_REPRICING",
            ]))
            result["observations"] = [
                *(result.get("observations") or []),
                f"v16_selected_direction={direction}",
                "v16_blocked_long_horizon_override=True",
                f"v16_counter_horizon={selected['counter_horizon_direction']}",
            ]
        result["evidence"] = result.get("observations", [])
        result["e1_trade_authority"] = False
        return result

    # No authoritative current structure: preserve context, but classify the
    # current market as unresolved rather than manufacturing a trend.
    result["market_state"] = "TRANSITION" if long_direction in DIRECTIONS else result.get("market_state", "UNCLEAR")
    result["trend_state"] = "NONE"
    result["dominant_direction"] = "NEUTRAL"
    result["directional_state"] = "UNRESOLVED"
    result["transition"] = "WATCH" if long_direction in DIRECTIONS else "ABSENT"
    result["transition_status"] = "WATCH" if long_direction in DIRECTIONS else "ABSENT"
    result["transition_confirmed"] = False
    result["transition_committed"] = False
    result["structure_alignment"] = "UNRESOLVED"
    result["e1_trade_authority"] = False
    result["conflicts"] = list(dict.fromkeys([
        *(result.get("conflicts") or []),
        "CURRENT_STRUCTURE_NOT_AUTHORITATIVE",
    ]))
    result["reasons"] = list(dict.fromkeys([
        *(result.get("reasons") or []),
        "V16_CURRENT_STRUCTURE_REQUIRED_FOR_TREND",
        "V16_LONG_HORIZON_IS_CONTEXT_NOT_STATE_OVERRIDE",
    ]))
    result["observations"] = [
        *(result.get("observations") or []),
        "v16_current_structure_authority=False",
        f"v16_context_direction={long_direction}",
        "v16_trend_promotion_blocked=True",
    ]
    result["evidence"] = result["observations"]
    return result


__all__ = ["analyze_e1_professional_v15", "select_dominant_direction_v15"]
