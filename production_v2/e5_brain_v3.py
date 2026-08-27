"""E5 Professional Location Brain V3.

Single brain, no sub-engines. Location analysis only; E9 remains decision authority.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class E5LocationResult:
    finding: str
    direction: str
    thesis: str
    location_quality: float
    observations: List[str]
    reasons: List[str]
    evidence: Dict[str, Any]
    reasoning_trace: List[str]


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def analyze_location(
    *,
    price: float,
    atr14: float,
    value: Optional[float] = None,
    value_distance_atr: Optional[float] = None,
    value_position: Optional[float] = None,
    structural_location: str = "UNKNOWN",
    distance_to_next_high_atr: Optional[float] = None,
    distance_to_next_low_atr: Optional[float] = None,
    liquidity_location: str = "UNKNOWN",
    sweep_high: bool = False,
    sweep_low: bool = False,
    extension_atr: Optional[float] = None,
    impulse_displacement_atr: Optional[float] = None,
    available_space_atr: Optional[float] = None,
    directional_context: str = "NEUTRAL",
    counter_evidence: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Evaluate whether current price location offers asymmetric opportunity.

    This function deliberately does not produce an execution direction. It evaluates
    location quality and exposes the numerical evidence used to reach that conclusion.
    """
    atr = max(_f(atr14), 1e-9)
    vd = _f(value_distance_atr, abs(price - _f(value)) / atr if value is not None else 0.0)
    vp = _f(value_position, 0.5)
    ext = _f(extension_atr)
    imp = _f(impulse_displacement_atr)
    space = _f(available_space_atr)
    hi = _f(distance_to_next_high_atr)
    lo = _f(distance_to_next_low_atr)
    counter = list(counter_evidence or [])

    reasons: List[str] = []
    trace: List[str] = []

    extension_risk = ext >= 2.0 or imp >= 2.5
    space_constrained = space > 0 and space < 1.0
    liquidity_at_location = liquidity_location.upper() not in {"", "UNKNOWN", "NONE"}

    trace.append(f"VALUE: distance_atr={vd:.3f}; position={vp:.3f}")
    trace.append(f"STRUCTURE: location={structural_location}")
    trace.append(f"LIQUIDITY: location={liquidity_location}; sweep_high={sweep_high}; sweep_low={sweep_low}")
    trace.append(f"EXTENSION: extension_atr={ext:.3f}; impulse_atr={imp:.3f}; risk={extension_risk}")
    trace.append(f"SPACE: available_atr={space:.3f}; next_high_atr={hi:.3f}; next_low_atr={lo:.3f}; constrained={space_constrained}")

    if extension_risk:
        reasons.append("EXTENSION_RISK")
    if liquidity_at_location:
        reasons.append("LIQUIDITY_EVENT_AT_LOCATION")
    if space_constrained:
        reasons.append("SPACE_CONSTRAINED")
    if counter:
        reasons.append("COUNTER_EVIDENCE_PRESENT")

    context = directional_context.upper()
    if context not in {"NEUTRAL", "UNKNOWN", ""}:
        if structural_location.upper() == "UNKNOWN":
            reasons.append("STRUCTURAL_LOCATION_UNRESOLVED")

    penalty = 0.0
    penalty += 0.30 if extension_risk else 0.0
    penalty += 0.25 if space_constrained else 0.0
    penalty += 0.15 if liquidity_at_location else 0.0
    penalty += min(0.30, 0.10 * len(counter))
    quality = max(0.0, min(1.0, 1.0 - penalty))

    if extension_risk and space_constrained:
        finding = "UNFAVORABLE_LOCATION"
        thesis = "WAIT_FOR_REPRICING_OR_NEW_SPACE"
    elif quality >= 0.75 and not counter:
        finding = "ADVANTAGEOUS_LOCATION_CANDIDATE"
        thesis = "LOCATION_HAS_ASYMMETRIC_SPACE"
    else:
        finding = "UNRESOLVED"
        thesis = "LOCATION_REQUIRES_REPRICING_OR_CONFIRMATION"

    trace.append(f"COUNTER-EVIDENCE: count={len(counter)}; items={counter}")
    trace.append(f"SYNTHESIS: quality={quality:.3f}; finding={finding}; thesis={thesis}")

    observations = [
        f"price={price:.6f}",
        f"atr14={atr:.6f}",
        f"value_distance_atr={vd:.3f}",
        f"value_position={vp:.3f}",
        f"structural_location={structural_location}",
        f"liquidity_location={liquidity_location}",
        f"sweep_high={sweep_high}",
        f"sweep_low={sweep_low}",
        f"extension_atr={ext:.3f}",
        f"impulse_displacement_atr={imp:.3f}",
        f"available_space_atr={space:.3f}",
        f"distance_to_next_high_atr={hi:.3f}",
        f"distance_to_next_low_atr={lo:.3f}",
        f"extension_risk={extension_risk}",
        f"space_constrained={space_constrained}",
        f"counter_evidence_count={len(counter)}",
        f"location_quality={quality:.3f}",
    ]

    evidence = {
        "price": price,
        "atr14": atr,
        "value_distance_atr": vd,
        "value_position": vp,
        "structural_location": structural_location,
        "liquidity_location": liquidity_location,
        "sweep_high": sweep_high,
        "sweep_low": sweep_low,
        "extension_atr": ext,
        "impulse_displacement_atr": imp,
        "available_space_atr": space,
        "distance_to_next_high_atr": hi,
        "distance_to_next_low_atr": lo,
        "directional_context": context,
        "counter_evidence": counter,
    }

    return asdict(E5LocationResult(
        finding=finding,
        direction=context,
        thesis=thesis,
        location_quality=quality,
        observations=observations,
        reasons=reasons,
        evidence=evidence,
        reasoning_trace=trace,
    ))


__all__ = ["E5LocationResult", "analyze_location"]
