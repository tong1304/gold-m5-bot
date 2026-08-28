"""E1 Professional State Machine v5.

V5 adds evidence arbitration between established context and recent price
pressure. A counter-move is classified as a pullback/threat until protected
structure is actually broken and accepted. E1 remains market-state only.
"""
from __future__ import annotations

from typing import Any

from .e1_professional_layer_v4 import analyze_e1_professional_v4

COUNTER_WINDOW = 5
ACCEPTANCE_BARS = 3
ACCEPTANCE_BUFFER_ATR = 0.15
PERSISTENCE_THRESHOLD = 0.60


def _direction(value: str | None) -> str:
    value = str(value or "").upper()
    if value in {"UP", "BULLISH"}:
        return "UP"
    if value in {"DOWN", "BEARISH"}:
        return "DOWN"
    return "NEUTRAL"


def _opposite(direction: str) -> str:
    return "DOWN" if direction == "UP" else "UP" if direction == "DOWN" else "NEUTRAL"


def _closed_body_direction(bar: dict[str, Any]) -> str:
    try:
        o, c = float(bar["open"]), float(bar["close"])
    except (KeyError, TypeError, ValueError):
        return "FLAT"
    return "UP" if c > o else "DOWN" if c < o else "FLAT"


def classify_recent_pressure(
    trend_direction: str,
    recent_directions: list[str],
    protected_level: float | None,
    recent_closes: list[float],
    atr: float,
) -> dict[str, Any]:
    """Separate counter-pressure from actual trend invalidation."""
    trend = _direction(trend_direction)
    counter = _opposite(trend)
    dirs = [_direction(x) for x in recent_directions]
    counter_count = sum(x == counter for x in dirs)
    trend_count = sum(x == trend for x in dirs)
    ratio = counter_count / max(len(dirs), 1)

    closes = [float(x) for x in recent_closes]
    buffer = max(float(atr or 0.0) * ACCEPTANCE_BUFFER_ATR, 1e-12)
    broken = False
    if protected_level is not None and closes:
        if trend == "DOWN":
            broken = closes[-1] > float(protected_level) + buffer
        elif trend == "UP":
            broken = closes[-1] < float(protected_level) - buffer

    if trend == "NEUTRAL":
        classification = "NO_DOMINANT_TREND"
        integrity = "UNRESOLVED"
    elif broken:
        classification = "STRUCTURE_BREAK_THREAT"
        integrity = "THREATENED"
    elif counter_count <= 1:
        classification = "PULLBACK_WITHIN_TREND" if counter_count else "TREND_CONTINUATION"
        integrity = "INTACT"
    else:
        # Persistence increases threat level, but does not become a reversal
        # until the protected structure is actually broken/accepted.
        classification = "COUNTER_PRESSURE_THREAT"
        integrity = "INTACT"

    return {
        "classification": classification,
        "trend_integrity": integrity,
        "trend_direction": trend,
        "counter_direction": counter,
        "counter_count": counter_count,
        "trend_count": trend_count,
        "counter_ratio": round(ratio, 3),
        "protected_level": protected_level,
        "acceptance_buffer_atr": ACCEPTANCE_BUFFER_ATR,
        "protected_level_broken": broken,
    }


def arbitrate_transition(
    prior_direction: str,
    current_direction: str,
    prior_state: str,
    candidate: bool,
    acceptance_confirmed: bool,
    persistence_score: float,
    protected_level: float | None,
    recent_closes: list[float],
    atr: float,
) -> dict[str, Any]:
    """Require structural acceptance before committing a regime transition."""
    prior = _direction(prior_direction)
    current = _direction(current_direction)
    persistence = float(persistence_score or 0.0)
    buffer = max(float(atr or 0.0) * ACCEPTANCE_BUFFER_ATR, 1e-12)
    structure_accepted = False
    if protected_level is not None and recent_closes:
        if prior == "DOWN" and current == "UP":
            structure_accepted = float(recent_closes[-1]) > float(protected_level) + buffer
        elif prior == "UP" and current == "DOWN":
            structure_accepted = float(recent_closes[-1]) < float(protected_level) - buffer

    committed = bool(
        candidate
        and prior in {"UP", "DOWN"}
        and current in {"UP", "DOWN"}
        and current != prior
        and acceptance_confirmed
        and structure_accepted
        and persistence >= PERSISTENCE_THRESHOLD
    )
    validated = bool(candidate and acceptance_confirmed and persistence >= 0.50)
    status = "COMMITTED" if committed else "VALIDATED" if validated else "WATCH" if candidate else "NONE"
    return {
        "status": status,
        "candidate": bool(candidate),
        "validated": validated,
        "committed": committed,
        "prior_state": str(prior_state or "UNKNOWN"),
        "prior_direction": prior,
        "current_direction": current,
        "acceptance_confirmed": bool(acceptance_confirmed),
        "structure_accepted": structure_accepted,
        "persistence_score": round(persistence, 3),
        "protected_level": protected_level,
    }


def _recent_context(bars: list[dict[str, Any]], trend_direction: str, protected_level: float | None, atr: float) -> dict[str, Any]:
    sample = [b for b in bars[-COUNTER_WINDOW:] if isinstance(b, dict)]
    directions = [_closed_body_direction(b) for b in sample]
    closes = [float(b["close"]) for b in sample if "close" in b]
    return classify_recent_pressure(trend_direction, directions, protected_level, closes, atr)


def analyze_e1_professional_v5(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    """V5 E1: arbitrate context vs recent pressure without trade authority."""
    base = analyze_e1_professional_v4(bars)
    if base.get("analysis_status") == "INCOMPLETE":
        return base

    output = dict(base)
    pr = dict(output.get("professional_reasoning") or {})
    state_machine = dict(pr.get("state_machine") or {})
    independent = dict(pr.get("independent_evidence") or {})
    structure = independent.get("structure") if isinstance(independent.get("structure"), dict) else {}
    volatility = independent.get("volatility") if isinstance(independent.get("volatility"), dict) else {}
    atr = float(volatility.get("atr14") or 0.0)

    current_direction = _direction(pr.get("direction") or output.get("directional_pressure"))
    previous_direction = _direction(state_machine.get("previous_direction"))
    if previous_direction == "NEUTRAL":
        previous_direction = current_direction
    protected_level = structure.get("recent_swing_high") if previous_direction == "DOWN" else structure.get("recent_swing_low") if previous_direction == "UP" else None

    clean_bars = [b for b in (bars or []) if isinstance(b, dict)]
    recent = _recent_context(clean_bars, previous_direction, protected_level, atr)
    candidate = bool(state_machine.get("transition_candidate") or output.get("transition") == "PRESENT")
    acceptance = dict(pr.get("closed_candle_acceptance") or {})
    acceptance_confirmed = bool(acceptance.get("confirmed"))
    persistence = float((pr.get("persistence") or {}).get("score", 0.0) or 0.0)
    recent_closes = [float(b["close"]) for b in clean_bars[-ACCEPTANCE_BARS:] if "close" in b]

    arbitration = arbitrate_transition(
        previous_direction,
        current_direction,
        str(state_machine.get("previous_regime") or "UNKNOWN"),
        candidate,
        acceptance_confirmed,
        persistence,
        protected_level,
        recent_closes,
        atr,
    )

    # Recent counter-pressure is not a regime reversal by itself.
    if output.get("market_state") in {"TREND_UP", "TREND_DOWN"} and recent["classification"] in {"PULLBACK_WITHIN_TREND", "COUNTER_PRESSURE_THREAT"} and not recent["protected_level_broken"]:
        output["transition"] = "ABSENT"
        output["transition_status"] = "NONE"
        output["transition_validated"] = False
        output["transition_committed"] = False

    # A V4 transition is retained only as committed when V5 independently proves it.
    if output.get("market_state") == "TRANSITION" and arbitration["status"] != "COMMITTED":
        output["transition"] = "PRESENT"
        output["transition_status"] = arbitration["status"]
        output["transition_validated"] = arbitration["validated"]
        output["transition_committed"] = False

    thesis = dict(pr.get("primary_thesis") or {})
    extra_counter = [] if recent["classification"] == "TREND_CONTINUATION" else [recent["classification"]]
    thesis["counter_evidence"] = list(dict.fromkeys(list(thesis.get("counter_evidence") or []) + extra_counter))
    if recent["classification"] == "PULLBACK_WITHIN_TREND":
        thesis["status"] = "CONFIRMED" if output.get("market_state") in {"TREND_UP", "TREND_DOWN"} else thesis.get("status", "DEVELOPING")

    state_machine.update({
        "version": "V5",
        "evidence_arbitration": arbitration,
        "recent_pressure": recent,
        "rule": "COUNTER_PRESSURE does not invalidate the dominant regime without protected-structure acceptance; COMMITTED requires acceptance + persistence >= 0.60",
    })
    pr["state_machine"] = state_machine
    pr["primary_thesis"] = thesis
    pr["recent_pressure"] = recent
    pr["evidence_arbitration"] = arbitration
    pr["decision_boundary"] = "MARKET_STATE_ONLY_NO_SETUP_NO_ENTRY_NO_RISK_NO_TRADE_DECISION"

    trace = list(output.get("reasoning_trace") or [])
    trace.extend([
        f"V5_ARBITRATION -> prior={previous_direction} current={current_direction} status={arbitration['status']}",
        f"V5_RECENT_PRESSURE -> {recent['classification']} integrity={recent['trend_integrity']} counter_ratio={recent['counter_ratio']:.3f}",
        f"V5_STRUCTURE_ACCEPTANCE -> broken={recent['protected_level_broken']} accepted={arbitration['structure_accepted']}",
        "V5_DECISION_BOUNDARY -> market-state only; no setup/entry/risk/trade authority",
    ])

    output["professional_reasoning"] = pr
    output["e1_contract_version"] = "PROFESSIONAL_STATE_MACHINE_V5"
    output["e1_trade_authority"] = False
    output["trade_decision_authority"] = False
    output["v5_recent_pressure"] = recent
    output["v5_evidence_arbitration"] = arbitration
    output["reasoning_trace"] = trace
    output["conflicts"] = list(dict.fromkeys(output.get("conflicts") or []))
    output["reasons"] = list(dict.fromkeys(output.get("reasons") or []))
    if recent["classification"] == "PULLBACK_WITHIN_TREND":
        output["reasons"].append("RECENT_COUNTER_MOVE_CLASSIFIED_AS_PULLBACK")
    elif recent["classification"] == "COUNTER_PRESSURE_THREAT":
        output["reasons"].append("COUNTER_PRESSURE_MONITORED_WITH_TREND_INTACT")
    if arbitration["status"] == "COMMITTED":
        output["reasons"].append("REGIME_TRANSITION_COMMITTED_V5")
    return output
