"""E1 V19 — professional market-state arbitration.

E1 answers one question only: what is the market doing right now?

V19 keeps confirmed structure as the highest authority, but fixes the
opposite failure mode of V18: a mixed/low-quality structural snapshot must
not automatically erase a persistent long-horizon trend. A trend may be
promoted by independent long-horizon persistence plus aligned EMA context
when there is no strong opposing structure. Short-term pressure never flips
regime by itself.
"""
from __future__ import annotations

from typing import Any

from .e1_professional_core_v18 import (
    _atr14,
    _direction,
    _independent_long_horizon,
    analyze_e1_professional_v18,
)

DIRECTIONS = {"UP", "DOWN"}
NON_DIRECTIONAL_STATES = {"RANGE", "COMPRESSION", "EXPANSION"}
MIN_STRUCTURE_QUALITY = 0.62
MIN_LONG_CONSENSUS = 2.0 / 3.0
MIN_LONG_PERSISTENCE = 2.0 / 3.0
MIN_LEAD_CONFIRMATIONS = 2


def _ema_supports(ema_relation: str, direction: str) -> bool:
    return _direction(ema_relation) == direction


def _persistent_long(long_direction: str, consensus: float, persistence: float) -> bool:
    return (
        long_direction in DIRECTIONS
        and float(consensus) >= MIN_LONG_CONSENSUS
        and float(persistence) >= MIN_LONG_PERSISTENCE
    )


def _long_horizon_lead_is_valid(*, long_direction: str, ema_relation: str,
                                pressure_direction: str, slopes: list[float]) -> bool:
    """Require independent confirmation before a non-structural trend lead."""
    if long_direction not in DIRECTIONS:
        return False
    confirmations = 0
    if _ema_supports(ema_relation, long_direction):
        confirmations += 1
    if _direction(pressure_direction) == long_direction:
        confirmations += 1
    signed = [x if long_direction == "UP" else -x for x in slopes]
    if sum(x > 0 for x in signed) >= 2:
        confirmations += 1
    return confirmations >= MIN_LEAD_CONFIRMATIONS


def select_dominant_regime_v19(*, structure_direction: str,
                               structure_quality: float,
                               structural_persistence: bool,
                               long_direction: str,
                               long_consensus: float,
                               long_persistence: float,
                               long_slopes: list[float],
                               pressure_direction: str,
                               ema_relation: str,
                               non_directional_state: str = "TRANSITION",
                               transition_confirmed: bool = False) -> dict[str, Any]:
    """Arbitrate regime using evidence hierarchy rather than raw vote counts."""
    sd = _direction(structure_direction)
    ld = _direction(long_direction)
    pd = _direction(pressure_direction)
    ema = _direction(ema_relation)
    quality = max(0.0, min(1.0, float(structure_quality)))

    strong_structure = sd in DIRECTIONS and quality >= MIN_STRUCTURE_QUALITY
    persistent_structure = strong_structure and bool(structural_persistence)
    persistent_long = _persistent_long(ld, long_consensus, long_persistence)

    # 1. Confirmed structural trend + persistent independent horizon.
    if persistent_structure and persistent_long and sd == ld:
        counter = pd in DIRECTIONS and pd != sd
        return {
            "market_state": f"TREND_{sd}", "dominant_direction": sd,
            "trend_confirmed": True,
            "transition": "WATCH" if counter else "ABSENT",
            "directional_state": "CONFIRMED",
            "reasons": (["COUNTER_PRESSURE"] if counter else []) +
                       ["STRUCTURE_AND_INDEPENDENT_LONG_HORIZON_CONVERGENCE"],
            "counter_evidence": ([f"PRESSURE={pd}"] if counter else []),
            "basis": "CONFIRMED_STRUCTURE_PLUS_LONG_HORIZON_CONVERGENCE",
        }

    # 2. Strong structure opposes a persistent horizon: structure wins until
    # persistent repricing is explicitly confirmed.
    if strong_structure and persistent_long and sd != ld:
        if transition_confirmed:
            return {
                "market_state": "TRANSITION", "dominant_direction": "NEUTRAL",
                "trend_confirmed": False, "transition": "CONFIRMED",
                "directional_state": "CONFLICTED",
                "reasons": ["STRUCTURE_VS_LONG_HORIZON_CONFLICT",
                            "PERSISTENT_STRUCTURAL_REPRICING_CONFIRMED"],
                "counter_evidence": [f"STRUCTURE={sd}", f"LONG_HORIZON={ld}"],
                "basis": "CONFIRMED_STRUCTURAL_REPRICING",
            }
        return {
            "market_state": f"TREND_{sd}" if persistent_structure else "TRANSITION",
            "dominant_direction": sd if persistent_structure else "NEUTRAL",
            "trend_confirmed": bool(persistent_structure),
            "transition": "WATCH",
            "directional_state": "DEVELOPING" if persistent_structure else "UNRESOLVED",
            "reasons": ["STRUCTURE_VS_LONG_HORIZON_CONFLICT",
                        "TRANSITION_REQUIRES_PERSISTENT_REPRICING"],
            "counter_evidence": [f"LONG_HORIZON={ld}"],
            "basis": "PERSISTENT_STRUCTURE_WITH_UNCONFIRMED_HORIZON_REPRICING"
                     if persistent_structure else "STRONG_STRUCTURE_CONFLICT_UNCONFIRMED",
        }

    # 3. If structure is mixed/weak rather than strongly opposite, persistent
    # long-horizon direction may lead the regime, but only with independent
    # context confirmation. This is the key V19 correction.
    if persistent_long and _long_horizon_lead_is_valid(
        long_direction=ld,
        ema_relation=ema,
        pressure_direction=pd,
        slopes=long_slopes,
    ):
        return {
            "market_state": f"TREND_{ld}", "dominant_direction": ld,
            "trend_confirmed": True, "transition": "WATCH",
            "directional_state": "CONFIRMED_LONG_HORIZON_LED",
            "reasons": ["PERSISTENT_LONG_HORIZON",
                        "NO_STRONG_OPPOSING_STRUCTURE",
                        "INDEPENDENT_CONTEXT_CONFIRMATION"],
            "counter_evidence": ([f"PRESSURE={pd}"] if pd in DIRECTIONS and pd != ld else []),
            "basis": "LONG_HORIZON_PERSISTENCE_WITH_CONTEXT_CONFIRMATION",
        }

    # 4. Preserve an explicit non-directional regime when there is no
    # sufficiently convergent directional evidence.
    base = str(non_directional_state or "TRANSITION").upper()
    if base in NON_DIRECTIONAL_STATES:
        return {
            "market_state": base, "dominant_direction": "NEUTRAL",
            "trend_confirmed": False, "transition": "ABSENT",
            "directional_state": "NEUTRAL",
            "reasons": ["NON_DIRECTIONAL_REGIME_PRESERVED",
                        "INSUFFICIENT_CONVERGENT_EVIDENCE_FOR_TREND"],
            "counter_evidence": [], "basis": "PRESERVED_NON_DIRECTIONAL_REGIME",
        }
    return {
        "market_state": "TRANSITION", "dominant_direction": "NEUTRAL",
        "trend_confirmed": False, "transition": "WATCH",
        "directional_state": "UNRESOLVED",
        "reasons": ["INSUFFICIENT_CONVERGENT_EVIDENCE_FOR_TREND"],
        "counter_evidence": [], "basis": "NO_CONVERGENT_REGIME",
    }


def analyze_e1_professional_v19(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    result = analyze_e1_professional_v18(bars)
    if result.get("analysis_status") != "COMPLETE":
        return result

    structure_state = str(result.get("structure_state") or "MIXED").upper()
    structure_direction = "UP" if structure_state == "BULLISH" else "DOWN" if structure_state == "BEARISH" else "NEUTRAL"
    structure_quality = float(result.get("structure_quality") or 0.0)
    structural_persistence = bool(result.get("structural_persistence"))
    independent = result.get("independent_evidence") or {}
    pressure = _direction((independent.get("pressure") or {}).get("direction"))
    ema = _direction((independent.get("ema_context") or {}).get("relation"))
    long = independent.get("long_horizon_independent") or _independent_long_horizon(bars or [])
    long_direction = _direction(long.get("direction"))
    long_consensus = float(long.get("consensus") or 0.0)
    long_persistence = float(long.get("persistence") or 0.0)
    long_slopes = [float(x) for x in (long.get("slopes") or [])]

    commitment = (result.get("professional_reasoning") or {}).get("transition_commitment") or {}
    transition_confirmed = bool(commitment) and all(bool(value) for value in commitment.values())

    decision = select_dominant_regime_v19(
        structure_direction=structure_direction,
        structure_quality=structure_quality,
        structural_persistence=structural_persistence,
        long_direction=long_direction,
        long_consensus=long_consensus,
        long_persistence=long_persistence,
        long_slopes=long_slopes,
        pressure_direction=pressure,
        ema_relation=ema,
        non_directional_state=result.get("market_state", "TRANSITION"),
        transition_confirmed=transition_confirmed,
    )

    result.update({
        "market_state": decision["market_state"],
        "trend_state": decision["dominant_direction"] if decision["trend_confirmed"] else "NONE",
        "dominant_direction": decision["dominant_direction"],
        "directional_state": decision["directional_state"],
        "transition": decision["transition"],
        "transition_status": decision["transition"],
        "transition_confirmed": decision["transition"] == "CONFIRMED",
        "transition_committed": decision["transition"] == "CONFIRMED",
        "structure_alignment": "ALIGNED" if structure_direction == long_direction and structure_direction in DIRECTIONS else "UNRESOLVED",
        "e1_trade_authority": False,
        "e1_contract_version": "PROFESSIONAL_MARKET_STATE_V19",
        "e1_engine_version": "PROFESSIONAL_MARKET_STATE_V19",
        "architecture": "E1_SINGLE_PROFESSIONAL_BRAIN_V19",
    })

    conflicts = list(result.get("conflicts") or [])
    if structure_direction in DIRECTIONS and long_direction in DIRECTIONS and structure_direction != long_direction:
        conflicts.append("STRUCTURE_VS_LONG_HORIZON_CONFLICT")
    result["conflicts"] = list(dict.fromkeys(conflicts))
    result["reasons"] = list(dict.fromkeys([
        *(result.get("reasons") or []), *decision["reasons"], "V19_EVIDENCE_HIERARCHY_APPLIED",
    ]))

    evidence = dict(independent)
    evidence["long_horizon_independent"] = long
    evidence["arbitration_v19"] = {
        "basis": decision["basis"],
        "structure_direction": structure_direction,
        "structure_quality": structure_quality,
        "structural_persistence": structural_persistence,
        "long_direction": long_direction,
        "long_consensus": long_consensus,
        "long_persistence": long_persistence,
        "long_slopes": long_slopes,
        "pressure_direction": pressure,
        "ema_relation": ema,
        "transition_commitment_confirmed": transition_confirmed,
    }
    result["independent_evidence"] = evidence

    result["observations"] = [
        *(result.get("observations") or []),
        f"v19_structure_direction={structure_direction}",
        f"v19_structure_quality={structure_quality:.3f}",
        f"v19_structural_persistence={structural_persistence}",
        f"v19_long_horizon_direction={long_direction}",
        f"v19_long_horizon_consensus={long_consensus:.3f}",
        f"v19_long_horizon_persistence={long_persistence:.3f}",
        f"v19_long_horizon_states={','.join(str(x) for x in (long.get('states') or []))}",
        f"v19_pressure_direction={pressure}",
        f"v19_ema_relation={ema}",
        f"v19_arbitration_basis={decision['basis']}",
        f"v19_trend_confirmed={decision['trend_confirmed']}",
    ]
    result["evidence"] = result["observations"]

    reasoning = dict(result.get("professional_reasoning") or {})
    reasoning.update({
        "market_state": result["market_state"],
        "trend_state": result["trend_state"],
        "dominant_direction": result["dominant_direction"],
        "structure_direction": structure_direction,
        "structure_quality": structure_quality,
        "structural_persistence": structural_persistence,
        "independent_long_horizon_direction": long_direction,
        "independent_long_horizon_consensus": long_consensus,
        "independent_long_horizon_persistence": long_persistence,
        "pressure_direction": pressure,
        "ema_context": ema,
        "evidence_hierarchy": "CONFIRMED_STRUCTURE > PERSISTENT_LONG_HORIZON+CONTEXT > SHORT_TERM_PRESSURE",
        "mixed_structure_does_not_erase_persistent_horizon": True,
        "short_term_pressure_is_not_regime_authority": True,
        "transition_policy": "REPRICING_CONFIRMATION_REQUIRED; COUNTER_HORIZON_ALONE_IS_NOT_A_REGIME_FLIP",
        "state_source_of_truth": "E1_V19_ARBITRATION",
        "reasoning_mirror_synchronized": True,
    })
    result["professional_reasoning"] = reasoning
    return result


__all__ = ["analyze_e1_professional_v19", "select_dominant_regime_v19"]
