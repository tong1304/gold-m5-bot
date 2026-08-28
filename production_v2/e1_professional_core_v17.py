"""E1 V17 — regime arbitration hardening.

E1 is a market-state brain, not a trade-entry brain. V17 prevents a single
structural snapshot from becoming TREND when the independent long-horizon
state disagrees. It also requires persistent structural evidence before a
trend is promoted, while allowing short-term counter-pressure inside an
established trend (normal pullback behaviour).
"""
from __future__ import annotations

from typing import Any

from .e1_professional_core_v16 import analyze_e1_professional_v16

DIRECTIONS = {"UP", "DOWN"}
MIN_STRUCTURE_QUALITY = 0.62
MIN_LONG_CONSENSUS = 2.0 / 3.0
MIN_LONG_PERSISTENCE = 2.0 / 3.0


def _direction(value: Any) -> str:
    return str(value or "NEUTRAL").upper()


def analyze_e1_professional_v17(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    result = analyze_e1_professional_v16(bars)
    if result.get("analysis_status") != "COMPLETE":
        return result

    structure = _direction(result.get("structure_state"))
    structure_direction = "UP" if structure == "BULLISH" else "DOWN" if structure == "BEARISH" else "NEUTRAL"
    long_info = result.get("directional_consensus") or {}
    long_direction = _direction(long_info.get("direction"))
    long_consensus = float(long_info.get("long_horizon_score") or 0.0)
    independent = result.get("independent_evidence") or {}
    persistence = independent.get("persistence") or {}
    long_persistence = float(persistence.get("long_horizon_score") or 0.0)
    structure_quality = float(result.get("structure_quality") or 0.0)
    structural_persistence = bool(result.get("structural_persistence"))
    pressure = _direction(result.get("directional_pressure"))
    recent = _direction(result.get("current_pressure"))

    strong_structure = structure_direction in DIRECTIONS and structure_quality >= MIN_STRUCTURE_QUALITY
    persistent_long = (
        long_direction in DIRECTIONS
        and long_consensus >= MIN_LONG_CONSENSUS
        and long_persistence >= MIN_LONG_PERSISTENCE
    )
    structural_trend = strong_structure and structural_persistence
    aligned_regime = structural_trend and persistent_long and structure_direction == long_direction
    structural_horizon_conflict = strong_structure and persistent_long and structure_direction != long_direction

    # Professional state rule:
    # - structure + persistent long horizon agree => established trend;
    # - structure and persistent long horizon disagree => transition/watch;
    # - short-term pressure alone may NOT flip an established trend.
    if structural_horizon_conflict:
        result["market_state"] = "TRANSITION"
        result["trend_state"] = "NONE"
        result["dominant_direction"] = "NEUTRAL"
        result["directional_state"] = "UNRESOLVED"
        result["transition"] = "WATCH"
        result["transition_status"] = "WATCH"
        result["transition_confirmed"] = False
        result["transition_committed"] = False
        result["structure_alignment"] = "UNRESOLVED"
        result["e1_trade_authority"] = False
        result["conflicts"] = list(dict.fromkeys([
            *(result.get("conflicts") or []),
            "STRUCTURE_VS_LONG_HORIZON_CONFLICT",
        ]))
        result["reasons"] = list(dict.fromkeys([
            *(result.get("reasons") or []),
            "V17_TREND_PROMOTION_BLOCKED_STRUCTURE_LONG_HORIZON_CONFLICT",
            "V17_TRANSITION_REQUIRES_PERSISTENT_REPRICING",
        ]))
        result["observations"] = [
            *(result.get("observations") or []),
            "v17_trend_promotion_blocked=True",
            f"v17_structure_direction={structure_direction}",
            f"v17_long_horizon_direction={long_direction}",
            f"v17_long_horizon_consensus={long_consensus:.3f}",
            f"v17_long_horizon_persistence={long_persistence:.3f}",
            f"v17_directional_pressure={pressure}",
            f"v17_recent_pressure={recent}",
        ]
    elif aligned_regime:
        direction = structure_direction
        result["market_state"] = "TREND_UP" if direction == "UP" else "TREND_DOWN"
        result["trend_state"] = direction
        result["dominant_direction"] = direction
        result["structure_alignment"] = "ALIGNED"
        result["transition_confirmed"] = False
        result["transition_committed"] = False
        # Counter-pressure is a pullback/auction condition, not an automatic
        # regime reversal. The long-horizon regime remains authoritative.
        if pressure in DIRECTIONS and pressure != direction:
            result["transition"] = "WATCH"
            result["transition_status"] = "WATCH"
            result["reasons"] = list(dict.fromkeys([
                *(result.get("reasons") or []),
                "V17_COUNTER_PRESSURE_WITHIN_ESTABLISHED_TREND",
            ]))
        result["e1_trade_authority"] = False
    else:
        # Do not manufacture a trend from weak/mixed evidence.
        if structure_direction not in DIRECTIONS or structure_quality < MIN_STRUCTURE_QUALITY:
            result["market_state"] = "RANGE" if result.get("market_state") == "RANGE" else "TRANSITION"
        else:
            result["market_state"] = "TRANSITION"
        result["trend_state"] = "NONE"
        result["dominant_direction"] = "NEUTRAL"
        result["directional_state"] = "UNRESOLVED"
        result["transition"] = "WATCH"
        result["transition_status"] = "WATCH"
        result["transition_confirmed"] = False
        result["transition_committed"] = False
        result["structure_alignment"] = "UNRESOLVED"
        result["e1_trade_authority"] = False
        result["reasons"] = list(dict.fromkeys([
            *(result.get("reasons") or []),
            "V17_INSUFFICIENT_CONVERGENT_EVIDENCE_FOR_TREND",
        ]))
        result["observations"] = [
            *(result.get("observations") or []),
            "v17_trend_promotion_blocked=True",
            f"v17_structure_direction={structure_direction}",
            f"v17_structure_quality={structure_quality:.3f}",
            f"v17_structural_persistence={structural_persistence}",
            f"v17_long_horizon_direction={long_direction}",
            f"v17_long_horizon_consensus={long_consensus:.3f}",
            f"v17_long_horizon_persistence={long_persistence:.3f}",
        ]

    reasoning = dict(result.get("professional_reasoning") or {})
    reasoning.update({
        "market_state": result.get("market_state"),
        "trend_state": result.get("trend_state"),
        "dominant_direction": result.get("dominant_direction"),
        "structure_direction": structure_direction,
        "structure_quality": structure_quality,
        "structural_persistence": structural_persistence,
        "long_horizon_direction": long_direction,
        "long_horizon_consensus": long_consensus,
        "long_horizon_persistence": long_persistence,
        "directional_pressure": pressure,
        "short_term_pressure_is_not_regime_authority": True,
        "trend_requires_structure_and_persistent_horizon_convergence": True,
        "conflict_policy": "STRUCTURE_VS_LONG_HORIZON_CONFLICT_EQUALS_TRANSITION_WATCH",
        "state_source_of_truth": "E1_V17_ARBITRATION",
        "reasoning_mirror_synchronized": True,
    })
    result["professional_reasoning"] = reasoning
    result["e1_contract_version"] = "PROFESSIONAL_MARKET_STATE_V17"
    result["e1_engine_version"] = "PROFESSIONAL_MARKET_STATE_V17"
    result["architecture"] = "E1_SINGLE_PROFESSIONAL_BRAIN_V17"
    result["evidence"] = result.get("observations", [])
    return result


__all__ = ["analyze_e1_professional_v17"]
