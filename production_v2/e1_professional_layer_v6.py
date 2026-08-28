"""E1 Professional State Arbitration V6.

V6 makes E1 behave like a professional market-state analyst: distinguish the
stable higher-horizon regime from short-term counter-pressure, and commit a
regime transition only when structural acceptance is already proven by V5.
E1 remains strictly market-state only.
"""
from __future__ import annotations

from typing import Any

from .e1_professional_layer_v5 import analyze_e1_professional_v5

MIN_LONG_CONSENSUS = 2 / 3
MIN_LONG_PERSISTENCE = 0.60
MIN_STRUCTURE_ALIGNMENT = 0.75
MIN_CONTEXT_STRENGTH = 0.72


def _dir(value: Any) -> str:
    value = str(value or "").upper()
    if value in {"UP", "BULLISH"}:
        return "UP"
    if value in {"DOWN", "BEARISH"}:
        return "DOWN"
    return "NEUTRAL"


def arbitrate_market_state_v6(
    *,
    core_state: str,
    core_direction: str,
    ema_direction: str,
    structure_direction: str,
    long_consensus: float,
    long_persistence: float,
    structure_alignment: float,
    ema_alignment: float,
    recent_pressure: str,
    protected_structure_intact: bool,
    transition_status: str,
) -> dict[str, Any]:
    """Reconcile dominant context, counter-pressure and transition evidence."""
    state = str(core_state or "UNCLEAR").upper()
    direction = _dir(core_direction)
    ema = _dir(ema_direction)
    structure = _dir(structure_direction)
    recent = _dir(recent_pressure)
    status = str(transition_status or "NONE").upper()

    context_votes = (
        direction in {"UP", "DOWN"}
        and ema == direction
        and structure == direction
        and float(long_consensus or 0.0) >= MIN_LONG_CONSENSUS
        and float(long_persistence or 0.0) >= MIN_LONG_PERSISTENCE
        and float(structure_alignment or 0.0) >= MIN_STRUCTURE_ALIGNMENT
        and float(ema_alignment or 0.0) >= 1.0
    )
    context_score = (
        0.25 * min(1.0, float(long_consensus or 0.0))
        + 0.25 * min(1.0, float(long_persistence or 0.0))
        + 0.25 * min(1.0, float(structure_alignment or 0.0))
        + 0.25 * min(1.0, float(ema_alignment or 0.0))
    )

    transition_committed = status == "COMMITTED"
    if transition_committed and direction in {"UP", "DOWN"}:
        final_state = "TREND_UP" if direction == "UP" else "TREND_DOWN"
        maturity = "ESTABLISHED"
        counter_class = "NONE" if recent == direction else "COUNTER_PRESSURE"
        transition = "ABSENT"
    elif context_votes and protected_structure_intact:
        # The professional default is to keep the dominant regime while a
        # short-term move runs against it. A counter move is not a reversal.
        final_state = "TREND_UP" if direction == "UP" else "TREND_DOWN"
        maturity = "ESTABLISHED"
        if recent in {_dir("DOWN") if direction == "UP" else _dir("UP")}:
            counter_class = "PULLBACK_WITHIN_TREND"
        elif recent == direction:
            counter_class = "TREND_CONTINUATION"
        else:
            counter_class = "COUNTER_PRESSURE"
        transition = "ABSENT"
    elif state in {"TREND_UP", "TREND_DOWN"} and direction in {"UP", "DOWN"} and protected_structure_intact:
        final_state = state
        maturity = "ESTABLISHED" if context_score >= MIN_CONTEXT_STRENGTH else "DEVELOPING"
        counter_class = "PULLBACK_WITHIN_TREND" if recent not in {"NEUTRAL", direction} else "TREND_CONTINUATION"
        transition = "ABSENT"
    elif state == "TRANSITION":
        final_state = "TRANSITION"
        maturity = "TRANSITION"
        counter_class = "TRANSITION_UNRESOLVED"
        transition = "PRESENT"
    else:
        final_state = state if state in {"RANGE", "COMPRESSION", "EXPANSION", "TRANSITION", "UNCLEAR"} else "UNCLEAR"
        maturity = "UNRESOLVED" if final_state == "UNCLEAR" else final_state
        counter_class = "NONE"
        transition = "PRESENT" if status in {"DETECTED", "WATCH", "VALIDATED"} else "ABSENT"

    return {
        "market_state": final_state,
        "direction": direction,
        "trend_maturity": maturity,
        "counter_pressure": counter_class,
        "transition": transition,
        "transition_commitment": transition_committed,
        "dominant_context_confirmed": bool(context_votes),
        "context_score": round(context_score, 3),
        "protected_structure_intact": bool(protected_structure_intact),
    }


def analyze_e1_professional_v6(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    """V6 E1: preserve valid regime context until genuine structural failure."""
    output = dict(analyze_e1_professional_v5(bars))
    if output.get("analysis_status") == "INCOMPLETE":
        return output

    pr = dict(output.get("professional_reasoning") or {})
    independent = dict(pr.get("independent_evidence") or {})
    structure_data = independent.get("structure") if isinstance(independent.get("structure"), dict) else {}
    ema_data = independent.get("ema_context") if isinstance(independent.get("ema_context"), dict) else {}
    persistence_data = independent.get("persistence") if isinstance(independent.get("persistence"), dict) else {}
    consensus_data = pr.get("directional_consensus") if isinstance(pr.get("directional_consensus"), dict) else {}
    state_machine = dict(pr.get("state_machine") or {})

    direction = _dir(pr.get("direction") or output.get("directional_pressure"))
    ema_direction = _dir(ema_data.get("relation"))
    structure_direction = _dir(structure_data.get("state"))
    long_consensus = float(consensus_data.get("long_horizon_score", 0.0) or 0.0)
    long_persistence = float(persistence_data.get("long_horizon_score", 0.0) or 0.0)
    structure_alignment = float(pr.get("structure_alignment", 0.0) or 0.0)
    ema_alignment = float(ema_data.get("alignment", 0.0) or 0.0)
    recent = dict(pr.get("recent_pressure") or output.get("v5_recent_pressure") or {})
    recent_pressure = _dir(recent.get("counter_direction")) if recent.get("classification") in {"PULLBACK_WITHIN_TREND", "COUNTER_PRESSURE_THREAT"} else direction
    protected_intact = not bool(recent.get("protected_level_broken"))
    transition_status = str(state_machine.get("transition_status") or output.get("transition_status") or "NONE")

    arbitration = arbitrate_market_state_v6(
        core_state=str(output.get("market_state") or "UNCLEAR"),
        core_direction=direction,
        ema_direction=ema_direction,
        structure_direction=structure_direction,
        long_consensus=long_consensus,
        long_persistence=long_persistence,
        structure_alignment=structure_alignment,
        ema_alignment=ema_alignment,
        recent_pressure=recent_pressure,
        protected_structure_intact=protected_intact,
        transition_status=transition_status,
    )

    old_state = str(output.get("market_state") or "UNCLEAR")
    output["market_state"] = arbitration["market_state"]
    output["trend_state"] = "UP" if direction == "UP" and arbitration["market_state"] == "TREND_UP" else "DOWN" if direction == "DOWN" and arbitration["market_state"] == "TREND_DOWN" else "NONE"
    output["transition"] = arbitration["transition"]
    output["transition_status"] = "COMMITTED" if arbitration["transition_commitment"] else "NONE" if arbitration["transition"] == "ABSENT" else transition_status
    output["transition_committed"] = arbitration["transition_commitment"]
    output["directional_state"] = "CONFIRMED" if arbitration["market_state"] in {"TREND_UP", "TREND_DOWN"} else output.get("directional_state", "UNRESOLVED")
    output["e1_contract_version"] = "PROFESSIONAL_STATE_MACHINE_V6"
    output["e1_trade_authority"] = False
    output["trade_decision_authority"] = False

    thesis = dict(pr.get("primary_thesis") or {})
    thesis["direction"] = direction
    thesis["status"] = "CONFIRMED" if arbitration["market_state"] in {"TREND_UP", "TREND_DOWN"} else thesis.get("status", "UNRESOLVED")
    thesis["arbitration"] = arbitration
    if arbitration["counter_pressure"] == "PULLBACK_WITHIN_TREND":
        thesis["counter_evidence"] = list(dict.fromkeys(list(thesis.get("counter_evidence") or []) + ["COUNTER_PRESSURE_CLASSIFIED_AS_PULLBACK"]))

    state_machine.update({
        "version": "V6",
        "market_state_before_v6": old_state,
        "market_state_after_v6": arbitration["market_state"],
        "dominant_context_confirmed": arbitration["dominant_context_confirmed"],
        "context_score": arbitration["context_score"],
        "counter_pressure": arbitration["counter_pressure"],
        "protected_structure_intact": arbitration["protected_structure_intact"],
        "rule": "Higher-horizon structure + EMA alignment + persistence outrank a short counter-move; reversal requires genuine protected-structure failure and accepted transition evidence.",
    })
    pr.update({
        "state_machine": state_machine,
        "primary_thesis": thesis,
        "market_state": arbitration["market_state"],
        "trend_maturity": arbitration["trend_maturity"],
        "counter_pressure": arbitration["counter_pressure"],
        "evidence_arbitration_v6": arbitration,
        "decision_boundary": "MARKET_STATE_ONLY_NO_SETUP_NO_ENTRY_NO_RISK_NO_TRADE_DECISION",
    })

    trace = list(output.get("reasoning_trace") or [])
    trace.extend([
        f"V6_CONTEXT_ARBITRATION -> state={old_state} -> {arbitration['market_state']} context_score={arbitration['context_score']:.3f}",
        f"V6_COUNTER_PRESSURE -> {arbitration['counter_pressure']} protected_structure_intact={arbitration['protected_structure_intact']}",
        f"V6_TRANSITION -> status={output['transition_status']} committed={arbitration['transition_commitment']}",
        "V6_DECISION_BOUNDARY -> market-state only; no setup/entry/risk/trade authority",
    ])

    output["professional_reasoning"] = pr
    output["reasoning_trace"] = trace
    output["v6_arbitration"] = arbitration
    output["reasons"] = list(dict.fromkeys(list(output.get("reasons") or [])))
    if old_state != arbitration["market_state"]:
        output["reasons"].append("V6_DOMINANT_CONTEXT_RECONCILED")
    if arbitration["counter_pressure"] == "PULLBACK_WITHIN_TREND":
        output["reasons"].append("V6_COUNTER_PRESSURE_IS_PULLBACK_NOT_REVERSAL")
    return output
