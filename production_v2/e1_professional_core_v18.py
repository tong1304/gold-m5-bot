"""E1 V18 — independent evidence arbitration.

V18 hardens the E1 market-state brain without touching E2-E9. The key rule is
that long-horizon direction must be independently measured from closed candles;
it may not be read back from an already-arbitrated field. Structure, horizon
persistence and pressure remain separate evidence sources.
"""
from __future__ import annotations

from typing import Any

from .e1_professional_core_v17 import analyze_e1_professional_v17

DIRECTIONS = {"UP", "DOWN"}
NON_DIRECTIONAL_STATES = {"RANGE", "COMPRESSION", "EXPANSION"}
MIN_STRUCTURE_QUALITY = 0.62
MIN_LONG_CONSENSUS = 2.0 / 3.0
MIN_LONG_PERSISTENCE = 2.0 / 3.0
HORIZONS = (10, 20, 40)
HORIZON_THRESHOLDS = (0.20, 0.30, 0.40)


def _direction(value: Any) -> str:
    value = str(value or "NEUTRAL").upper()
    return value if value in DIRECTIONS else "NEUTRAL"


def _num(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value == value and abs(value) != float("inf") else None


def _atr14(bars: list[dict[str, Any]]) -> float:
    rows = bars[-14:]
    trs: list[float] = []
    previous_close: float | None = None
    for bar in rows:
        high, low, close = (_num(bar.get(k)) for k in ("high", "low", "close"))
        if high is None or low is None or close is None:
            return 0.0
        trs.append(high - low if previous_close is None else max(high - low, abs(high - previous_close), abs(low - previous_close)))
        previous_close = close
    return sum(trs) / len(trs) if trs else 0.0


def _slope(closes: list[float], atr: float, bars: int) -> float:
    if atr <= 0 or len(closes) <= bars:
        return 0.0
    return (closes[-1] - closes[-1 - bars]) / atr


def _independent_long_horizon(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Measure long-horizon direction directly from prices, never from E1 output."""
    closes = [_num(b.get("close")) for b in bars]
    closes = [x for x in closes if x is not None]
    atr = _atr14(bars)
    slopes = [_slope(closes, atr, n) for n in HORIZONS]
    states = ["UP" if slope >= threshold else "DOWN" if slope <= -threshold else "FLAT" for slope, threshold in zip(slopes, HORIZON_THRESHOLDS)]
    up, down = states.count("UP"), states.count("DOWN")
    direction = "UP" if up > down else "DOWN" if down > up else "NEUTRAL"
    consensus = max(up, down) / 3.0
    if direction == "UP":
        persistence = sum(s >= t for s, t in zip(slopes, HORIZON_THRESHOLDS)) / 3.0
    elif direction == "DOWN":
        persistence = sum(s <= -t for s, t in zip(slopes, HORIZON_THRESHOLDS)) / 3.0
    else:
        persistence = 0.0
    return {"direction": direction, "consensus": consensus, "persistence": persistence, "slopes": slopes, "states": states, "independent": True}


def select_dominant_regime_v18(*, structure_direction: str, structure_quality: float, structural_persistence: bool, long_direction: str, long_consensus: float, long_persistence: float, pressure_direction: str, ema_relation: str, non_directional_state: str = "TRANSITION") -> dict[str, Any]:
    """Require convergent independent evidence for TREND; preserve valid non-trend regimes."""
    sd, ld, pd = _direction(structure_direction), _direction(long_direction), _direction(pressure_direction)
    ema = _direction(ema_relation)
    quality = max(0.0, min(1.0, float(structure_quality)))
    strong_structure = sd in DIRECTIONS and quality >= MIN_STRUCTURE_QUALITY
    persistent_structure = strong_structure and bool(structural_persistence)
    persistent_long = ld in DIRECTIONS and float(long_consensus) >= MIN_LONG_CONSENSUS and float(long_persistence) >= MIN_LONG_PERSISTENCE
    reasons: list[str] = []

    if strong_structure and persistent_long and sd != ld:
        return {"market_state":"TRANSITION","dominant_direction":"NEUTRAL","trend_confirmed":False,"transition":"WATCH","directional_state":"UNRESOLVED","reasons":["STRUCTURE_VS_LONG_HORIZON_CONFLICT","TREND_PROMOTION_BLOCKED","TRANSITION_REQUIRES_PERSISTENT_REPRICING"],"counter_evidence":[f"LONG_HORIZON={ld}",f"STRUCTURE={sd}"],"basis":"INDEPENDENT_STRUCTURE_LONG_HORIZON_CONFLICT"}

    if persistent_structure and persistent_long and sd == ld:
        if pd in DIRECTIONS and pd != sd:
            reasons.append("COUNTER_PRESSURE")
        return {"market_state":"TREND_UP" if sd == "UP" else "TREND_DOWN","dominant_direction":sd,"trend_confirmed":True,"transition":"WATCH" if reasons else "ABSENT","directional_state":"CONFIRMED","reasons":reasons,"counter_evidence":[f"PRESSURE={pd}"] if reasons else [],"basis":"STRUCTURE_AND_INDEPENDENT_LONG_HORIZON_CONVERGENCE"}

    base = str(non_directional_state or "TRANSITION").upper()
    if base in NON_DIRECTIONAL_STATES and not (sd in DIRECTIONS and ld in DIRECTIONS and sd != ld):
        return {"market_state":base,"dominant_direction":"NEUTRAL","trend_confirmed":False,"transition":"ABSENT","directional_state":"NEUTRAL","reasons":["NON_DIRECTIONAL_REGIME_PRESERVED","INSUFFICIENT_CONVERGENT_EVIDENCE_FOR_TREND"],"counter_evidence":[],"basis":"PRESERVED_NON_DIRECTIONAL_REGIME"}

    return {"market_state":"TRANSITION","dominant_direction":"NEUTRAL","trend_confirmed":False,"transition":"WATCH","directional_state":"UNRESOLVED","reasons":["INSUFFICIENT_CONVERGENT_EVIDENCE_FOR_TREND"],"counter_evidence":[],"basis":"NO_CONVERGENT_REGIME"}


def analyze_e1_professional_v18(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    result = analyze_e1_professional_v17(bars)
    if result.get("analysis_status") != "COMPLETE":
        return result

    structure_state = str(result.get("structure_state") or "MIXED").upper()
    structure_direction = "UP" if structure_state == "BULLISH" else "DOWN" if structure_state == "BEARISH" else "NEUTRAL"
    long = _independent_long_horizon(bars or [])
    independent = result.get("independent_evidence") or {}
    pressure = _direction((independent.get("pressure") or {}).get("direction"))
    ema = _direction((independent.get("ema_context") or {}).get("relation"))
    decision = select_dominant_regime_v18(structure_direction=structure_direction, structure_quality=float(result.get("structure_quality") or 0.0), structural_persistence=bool(result.get("structural_persistence")), long_direction=long["direction"], long_consensus=long["consensus"], long_persistence=long["persistence"], pressure_direction=pressure, ema_relation=ema, non_directional_state=result.get("market_state", "TRANSITION"))

    result.update({"market_state":decision["market_state"],"trend_state":decision["dominant_direction"] if decision["trend_confirmed"] else "NONE","dominant_direction":decision["dominant_direction"],"directional_state":decision["directional_state"],"transition":decision["transition"],"transition_status":decision["transition"],"transition_confirmed":False,"transition_committed":False,"e1_trade_authority":False,"e1_contract_version":"PROFESSIONAL_MARKET_STATE_V18","e1_engine_version":"PROFESSIONAL_MARKET_STATE_V18","architecture":"E1_SINGLE_PROFESSIONAL_BRAIN_V18"})
    if structure_direction in DIRECTIONS and long["direction"] in DIRECTIONS and structure_direction != long["direction"]:
        result["conflicts"] = list(dict.fromkeys([*(result.get("conflicts") or []),"STRUCTURE_VS_LONG_HORIZON_CONFLICT"]))
    result["reasons"] = list(dict.fromkeys([*(result.get("reasons") or []),*decision["reasons"]]))

    evidence = dict(independent)
    evidence["long_horizon_independent"] = long
    evidence["arbitration_v18"] = {"basis":decision["basis"],"structure_direction":structure_direction,"structure_quality":float(result.get("structure_quality") or 0.0),"structural_persistence":bool(result.get("structural_persistence")),"long_direction":long["direction"],"long_consensus":long["consensus"],"long_persistence":long["persistence"],"pressure_direction":pressure,"ema_relation":ema}
    result["independent_evidence"] = evidence
    result["observations"] = [*(result.get("observations") or []),f"v18_independent_long_horizon_direction={long['direction']}",f"v18_independent_long_horizon_consensus={long['consensus']:.3f}",f"v18_independent_long_horizon_persistence={long['persistence']:.3f}",f"v18_independent_long_horizon_states={','.join(long['states'])}",f"v18_arbitration_basis={decision['basis']}",f"v18_trend_confirmed={decision['trend_confirmed']}"]
    result["evidence"] = result["observations"]
    reasoning = dict(result.get("professional_reasoning") or {})
    reasoning.update({"market_state":result["market_state"],"dominant_direction":result["dominant_direction"],"trend_state":result["trend_state"],"structure_direction":structure_direction,"structure_quality":float(result.get("structure_quality") or 0.0),"structural_persistence":bool(result.get("structural_persistence")),"independent_long_horizon_direction":long["direction"],"independent_long_horizon_consensus":long["consensus"],"independent_long_horizon_persistence":long["persistence"],"pressure_direction":pressure,"ema_context":ema,"trend_requires_structure_and_independent_horizon_convergence":True,"short_term_pressure_is_not_regime_authority":True,"transition_policy":"CONFLICT_OR_INSUFFICIENT_CONVERGENCE_EQUALS_WATCH","state_source_of_truth":"E1_V18_ARBITRATION","reasoning_mirror_synchronized":True})
    result["professional_reasoning"] = reasoning
    result["confidence"] = min(float(result.get("confidence") or 0.0),0.82) if not decision["trend_confirmed"] else float(result.get("confidence") or 0.0)
    return result


__all__ = ["analyze_e1_professional_v18","select_dominant_regime_v18"]
