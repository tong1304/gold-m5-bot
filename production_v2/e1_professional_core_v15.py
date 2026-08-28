"""E1 V17 — professional market-state arbitration.

E1 describes the market state only.  A structural label is not sufficient to
call a trend when the current directional pressure and persistent long-horizon
context both disagree with that structure.  Such three-way disagreement is a
transition/watch condition until repricing becomes persistent.
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
    pressure_direction: str = "NEUTRAL",
    recent_direction: str = "NEUTRAL",
) -> dict[str, Any]:
    """Select the current M5 market-state direction.

    Arbitration:
    1. Persistent current structure has first authority.
    2. Mixed/weak structure cannot create a trend from context alone.
    3. Long-horizon and EMA evidence are context, not automatic overrides.
    4. If structure conflicts with both persistent horizon and current/recent
       pressure, the market is unresolved/transition rather than a trend.
    5. A non-persistent structural label cannot win a three-way conflict.
    """
    sd = str(structure_direction or "NEUTRAL").upper()
    ld = str(long_direction or "NEUTRAL").upper()
    ema = str(ema_relation or "NEUTRAL").upper()
    pd = str(pressure_direction or "NEUTRAL").upper()
    rd = str(recent_direction or "NEUTRAL").upper()
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

    # A professional state classifier must not call a trend from one lagging
    # structural snapshot when both the current/recent pressure and persistent
    # horizon are pointing the other way.
    three_way_conflict = (
        strong_structure
        and persistent_long
        and sd != ld
        and pd == ld
        and rd in {ld, "NEUTRAL"}
    )
    if three_way_conflict:
        return {
            "direction": "NEUTRAL",
            "basis": "THREE_WAY_DIRECTIONAL_CONFLICT",
            "blocked_override": True,
            "counter_horizon_direction": ld,
            "ema_context": ema,
            "ema_gap": gap,
        }

    if persistent_structure:
        return {
            "direction": sd,
            "basis": "PERSISTENT_CURRENT_STRUCTURE",
            "blocked_override": bool(opposite_horizon),
            "counter_horizon_direction": ld if ld in DIRECTIONS and ld != sd else "NEUTRAL",
            "ema_context": ema,
            "ema_gap": gap,
        }

    if opposite_horizon:
        return {
            "direction": sd,
            "basis": "STRUCTURE_FIRST_COUNTER_HORIZON",
            "blocked_override": True,
            "counter_horizon_direction": ld,
            "ema_context": ema,
            "ema_gap": gap,
        }

    if usable_structure and persistent_long and sd == ld and ema == ld and abs(gap) >= 0.50:
        return {
            "direction": sd,
            "basis": "CURRENT_STRUCTURE_WITH_HORIZON_EMA_SUPPORT",
            "blocked_override": False,
            "counter_horizon_direction": "NEUTRAL",
            "ema_context": ema,
            "ema_gap": gap,
        }

    if strong_structure and sd == ema and abs(gap) >= 0.50:
        return {
            "direction": sd,
            "basis": "STRUCTURE_EMA_ALIGNMENT",
            "blocked_override": False,
            "counter_horizon_direction": ld if ld in DIRECTIONS and ld != sd else "NEUTRAL",
            "ema_context": ema,
            "ema_gap": gap,
        }

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
    pressure_direction = str(pressure.get("direction") or result.get("directional_pressure") or "NEUTRAL").upper()
    recent_direction = str(result.get("current_pressure") or "NEUTRAL").upper()
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
        pressure_direction=pressure_direction,
        recent_direction=recent_direction,
    )

    result["e1_contract_version"] = "PROFESSIONAL_MARKET_STATE_V17"
    result["e1_engine_version"] = "PROFESSIONAL_MARKET_STATE_V17"
    result["architecture"] = "E1_SINGLE_PROFESSIONAL_BRAIN_V17"
    result["professional_reasoning"] = {
        **pr,
        "structure_first": True,
        "dominant_basis": selected["basis"],
        "counter_horizon_direction": selected["counter_horizon_direction"],
        "long_horizon_is_context_not_state_override": True,
        "transition_requires": "PERSISTENT_STRUCTURAL_REPRICING",
        "pressure_direction": pressure_direction,
        "recent_direction": recent_direction,
    }

    if selected["direction"] in DIRECTIONS:
        direction = selected["direction"]
        result["market_state"] = "TREND_UP" if direction == "UP" else "TREND_DOWN"
        result["trend_state"] = direction
        result["dominant_direction"] = direction
        result["directional_pressure"] = pressure_direction
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
                "V17_STRUCTURE_FIRST_COUNTER_HORIZON",
                "V17_LONG_HORIZON_IS_CONTEXT_NOT_STATE_OVERRIDE",
                "V17_TRANSITION_REQUIRES_STRUCTURAL_REPRICING",
            ]))
            result["observations"] = [
                *(result.get("observations") or []),
                f"v17_selected_direction={direction}",
                "v17_blocked_long_horizon_override=True",
                f"v17_counter_horizon={selected['counter_horizon_direction']}",
            ]
        result["evidence"] = result.get("observations", [])
        result["e1_trade_authority"] = False
        return result

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
    if selected["basis"] == "THREE_WAY_DIRECTIONAL_CONFLICT":
        result["conflicts"] = list(dict.fromkeys([
            *result["conflicts"],
            "THREE_WAY_DIRECTIONAL_CONFLICT",
        ]))
        result["reasons"] = list(dict.fromkeys([
            *(result.get("reasons") or []),
            "V17_THREE_WAY_CONFLICT_REQUIRES_TRANSITION_WATCH",
            "V17_CURRENT_PRESSURE_AND_LONG_HORIZON_AGREE_AGAINST_STRUCTURE",
        ]))
        result["observations"] = [
            *(result.get("observations") or []),
            "v17_trend_promotion_blocked=True",
            f"v17_structure_direction={structure_direction}",
            f"v17_pressure_direction={pressure_direction}",
            f"v17_long_direction={long_direction}",
            f"v17_recent_direction={recent_direction}",
        ]
    else:
        result["reasons"] = list(dict.fromkeys([
            *(result.get("reasons") or []),
            "V17_CURRENT_STRUCTURE_REQUIRED_FOR_TREND",
            "V17_LONG_HORIZON_IS_CONTEXT_NOT_STATE_OVERRIDE",
        ]))
        result["observations"] = [
            *(result.get("observations") or []),
            "v17_current_structure_authority=False",
            f"v17_context_direction={long_direction}",
            "v17_trend_promotion_blocked=True",
        ]
    result["evidence"] = result["observations"]
    return result


__all__ = ["analyze_e1_professional_v15", "select_dominant_direction_v15"]
