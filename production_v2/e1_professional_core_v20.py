"""E1 V20 — professional market-state arbitration wrapper.

V20 preserves the validated V19 calculations but fixes a critical semantic
problem observed in live telemetry: TRANSITION was being used for weak/mixed
structure even when independent long-horizon evidence, EMA context and
multiple long horizons agreed on a direction. A professional market-state
engine should distinguish:

- TRANSITION/WATCH: established regime is being challenged by persistent
  opposing repricing;
- TREND_* / DEVELOPING: directional regime is supported by persistent
  independent evidence, while structure is not strongly opposing it.

E1 remains descriptive only. It has no trade-decision authority.
"""
from __future__ import annotations

from typing import Any

from .e1_professional_core_v19 import analyze_e1_professional_v19

DIRECTIONS = {"UP", "DOWN"}
MIN_LONG_CONSENSUS = 2.0 / 3.0
MIN_LONG_PERSISTENCE = 2.0 / 3.0
STRONG_STRUCTURE = 0.65


def _direction(value: Any) -> str:
    value = str(value or "NEUTRAL").upper()
    return value if value in DIRECTIONS else "NEUTRAL"


def _persistent_long(info: dict[str, Any]) -> bool:
    direction = _direction(info.get("direction"))
    return (
        direction in DIRECTIONS
        and float(info.get("consensus") or 0.0) >= MIN_LONG_CONSENSUS
        and float(info.get("persistence") or 0.0) >= MIN_LONG_PERSISTENCE
    )


def _ema_supports(result: dict[str, Any], direction: str) -> bool:
    independent = result.get("independent_evidence") or {}
    ema = independent.get("ema_context") or {}
    return _direction(ema.get("relation")) == direction


def _long_slopes_support(info: dict[str, Any], direction: str) -> bool:
    slopes = [float(x) for x in (info.get("slopes") or [])]
    if len(slopes) < 2:
        return False
    signed = [x if direction == "UP" else -x for x in slopes]
    return sum(x > 0 for x in signed) >= 2


def analyze_e1_professional_v20(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    result = analyze_e1_professional_v19(bars)
    if result.get("analysis_status") != "COMPLETE":
        return result

    independent = result.get("independent_evidence") or {}
    long_info = independent.get("long_horizon_independent") or {}
    long_direction = _direction(long_info.get("direction"))
    long_persistent = _persistent_long(long_info)
    ema_support = _ema_supports(result, long_direction) if long_direction in DIRECTIONS else False
    slope_support = _long_slopes_support(long_info, long_direction) if long_direction in DIRECTIONS else False

    structure_state = str(result.get("structure_state") or "MIXED").upper()
    structure_direction = _direction("UP" if structure_state == "BULLISH" else "DOWN" if structure_state == "BEARISH" else "NEUTRAL")
    structure_quality = float(result.get("structure_quality") or 0.0)
    strong_opposing_structure = (
        structure_direction in DIRECTIONS
        and structure_quality >= STRONG_STRUCTURE
        and long_direction in DIRECTIONS
        and structure_direction != long_direction
    )

    # Promotion rule: persistent long-horizon direction + EMA context + at
    # least two long horizons is enough for a DEVELOPING regime when there is
    # no strong opposing structure. This is not an entry signal.
    long_led_developing = (
        long_persistent
        and ema_support
        and slope_support
        and not strong_opposing_structure
    )

    old_state = str(result.get("market_state") or "UNCLEAR")
    promoted = False
    if long_led_developing and old_state == "TRANSITION":
        result.update({
            "market_state": "TREND_UP" if long_direction == "UP" else "TREND_DOWN",
            "trend_state": long_direction,
            "trend_maturity": "DEVELOPING",
            "trend_confirmed": False,
            "dominant_direction": long_direction,
            "directional_state": "DEVELOPING",
            "transition": "WATCH",
            "transition_status": "WATCH",
            "transition_confirmed": False,
            "transition_committed": False,
            "regime_stress": "ABSENT",
            "e1_trade_authority": False,
        })
        promoted = True

    reasons = list(result.get("reasons") or [])
    if promoted:
        reasons = [
            x for x in reasons
            if x not in {
                "INSUFFICIENT_CONVERGENT_EVIDENCE_FOR_TREND",
                "TRANSITION_REQUIRES_PERSISTENT_REPRICING",
            }
        ]
        reasons.extend([
            "V20_LONG_HORIZON_REGIME_PROMOTION",
            "V20_EMA_CONTEXT_CONFIRMATION",
            "V20_MULTI_HORIZON_PERSISTENCE_CONFIRMATION",
            "V20_NO_STRONG_OPPOSING_STRUCTURE",
            "V20_DEVELOPING_TREND_REQUIRES_DOWNSTREAM_CONFIRMATION",
        ])
    elif strong_opposing_structure and long_persistent:
        reasons.extend([
            "V20_STRONG_STRUCTURE_OPPOSES_LONG_HORIZON",
            "V20_TRANSITION_REQUIRES_PERSISTENT_REPRICING",
        ])
    result["reasons"] = list(dict.fromkeys(reasons))

    conflicts = list(result.get("conflicts") or [])
    if strong_opposing_structure:
        conflicts.append("V20_STRONG_STRUCTURE_VS_LONG_HORIZON")
    elif promoted:
        conflicts = [x for x in conflicts if x != "STRUCTURE_VS_LONG_HORIZON_CONFLICT"]
    result["conflicts"] = list(dict.fromkeys(conflicts))

    observations = list(result.get("observations") or [])
    observations.extend([
        f"v20_long_horizon_direction={long_direction}",
        f"v20_long_horizon_persistent={long_persistent}",
        f"v20_ema_support={ema_support}",
        f"v20_long_slope_support={slope_support}",
        f"v20_structure_direction={structure_direction}",
        f"v20_structure_quality={structure_quality:.3f}",
        f"v20_strong_opposing_structure={strong_opposing_structure}",
        f"v20_old_state={old_state}",
        f"v20_promoted_to_developing_trend={promoted}",
        f"v20_final_state={result.get('market_state')}",
    ])
    result["observations"] = observations
    result["evidence"] = observations

    independent = dict(result.get("independent_evidence") or {})
    independent["arbitration_v20"] = {
        "old_state": old_state,
        "final_state": result.get("market_state"),
        "promoted": promoted,
        "long_direction": long_direction,
        "long_persistent": long_persistent,
        "ema_support": ema_support,
        "long_slope_support": slope_support,
        "structure_direction": structure_direction,
        "structure_quality": structure_quality,
        "strong_opposing_structure": strong_opposing_structure,
        "rule": "PERSISTENT_LONG_HORIZON + EMA_CONTEXT + 2_LONG_HORIZONS + NO_STRONG_OPPOSING_STRUCTURE",
    }
    result["independent_evidence"] = independent

    reasoning = dict(result.get("professional_reasoning") or {})
    reasoning.update({
        "market_state": result.get("market_state"),
        "trend_state": result.get("trend_state"),
        "trend_maturity": result.get("trend_maturity"),
        "trend_confirmed": result.get("trend_confirmed"),
        "dominant_direction": result.get("dominant_direction"),
        "v20_long_horizon_direction": long_direction,
        "v20_long_horizon_persistent": long_persistent,
        "v20_ema_context_support": ema_support,
        "v20_multi_horizon_support": slope_support,
        "v20_strong_opposing_structure": strong_opposing_structure,
        "v20_promotion_applied": promoted,
        "v20_transition_definition": "OPPOSING_PERSISTENT_REPRICING_ONLY",
        "state_source_of_truth": "E1_V20_ARBITRATION",
        "reasoning_mirror_synchronized": True,
        "e1_trade_authority": False,
    })
    result["professional_reasoning"] = reasoning
    result["e1_contract_version"] = "PROFESSIONAL_MARKET_STATE_V20"
    result["e1_engine_version"] = "PROFESSIONAL_MARKET_STATE_V20"
    result["architecture"] = "E1_SINGLE_PROFESSIONAL_BRAIN_V20"
    result["e1_trade_authority"] = False
    return result


__all__ = ["analyze_e1_professional_v20"]
