"""E1 Professional Market-State Brain V9.

V9 preserves V8's hierarchical market-state arbitration and fixes the
observability contract: telemetry must be derived from the authoritative E1
output, never from stale nested reasoning fields inherited from older layers.
E1 remains market-state only and has no trade authority.
"""
from __future__ import annotations

from typing import Any

from .e1_professional_layer_v8 import analyze_e1_professional_v8


def _authoritative(output: dict[str, Any], key: str, default: Any = None) -> Any:
    value = output.get(key)
    return default if value is None else value


def normalize_e1_telemetry(output: dict[str, Any]) -> dict[str, Any]:
    """Return one internally consistent E1 state view.

    Top-level V8 fields are authoritative. Nested ``professional_reasoning``
    fields may contain historical values from V6/V7 and therefore must never
    override the current E1 state.
    """
    reasoning = output.get("professional_reasoning")
    if not isinstance(reasoning, dict):
        reasoning = {}

    keys = (
        "market_state",
        "trend_state",
        "directional_pressure",
        "current_pressure",
        "counter_pressure",
        "market_phase",
        "transition",
        "transition_status",
        "transition_committed",
        "structure_state",
        "volatility_state",
        "compression",
        "expansion",
        "directional_state",
        "dominant_direction",
    )
    normalized: dict[str, Any] = {}
    for key in keys:
        if key in output and output[key] is not None:
            normalized[key] = output[key]
        elif key in reasoning and reasoning[key] is not None:
            normalized[key] = reasoning[key]

    dominant = normalized.get("dominant_direction")
    state = normalized.get("market_state")
    if dominant in {"UP", "DOWN"}:
        expected_state = "TREND_UP" if dominant == "UP" else "TREND_DOWN"
        expected_trend = dominant
        if state in {"TREND_UP", "TREND_DOWN"}:
            state = expected_state
        normalized["market_state"] = state or expected_state
        normalized["trend_state"] = expected_trend
        normalized["directional_pressure"] = dominant
    else:
        normalized.setdefault("trend_state", "NONE")

    # A pullback is a phase/current-pressure fact, not a regime reversal.
    if normalized.get("counter_pressure") == "PULLBACK_WITHIN_TREND":
        if normalized.get("trend_state") in {"UP", "DOWN"}:
            normalized["directional_pressure"] = normalized["trend_state"]

    return normalized


def _sync_professional_reasoning(output: dict[str, Any]) -> None:
    """Synchronize display-facing reasoning fields with authoritative E1 state."""
    telemetry = normalize_e1_telemetry(output)
    reasoning = dict(output.get("professional_reasoning") or {})

    for key, value in telemetry.items():
        if value is not None:
            reasoning[key] = value

    # Keep the hierarchy explicit for downstream readers and operators.
    reasoning["decision_boundary"] = "MARKET_STATE_ONLY_NO_SETUP_NO_ENTRY_NO_RISK_NO_TRADE_DECISION"
    reasoning["e1_telemetry_authority"] = "TOP_LEVEL_E1_OUTPUT"
    reasoning["rule"] = (
        "Structure and long-horizon context define dominant regime; short-term "
        "counter-pressure changes phase, not regime. Nested legacy reasoning "
        "fields cannot override authoritative E1 state."
    )
    output["professional_reasoning"] = reasoning


def analyze_e1_professional_v9(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    """V9 E1: V8 decision logic plus a strict consistency/telemetry contract."""
    output = dict(analyze_e1_professional_v8(bars))
    if output.get("analysis_status") == "INCOMPLETE":
        return output

    _sync_professional_reasoning(output)
    telemetry = normalize_e1_telemetry(output)

    output.update(telemetry)
    output["e1_contract_version"] = "PROFESSIONAL_MARKET_STATE_V9"
    output["e1_trade_authority"] = False
    output["trade_decision_authority"] = False
    output["v9_telemetry_contract"] = {
        "authority": "TOP_LEVEL_E1_OUTPUT",
        "nested_reasoning_is_display_only": True,
        "pullback_does_not_reverse_regime": True,
    }

    trace = list(output.get("reasoning_trace") or [])
    trace.append("V9_TELEMETRY -> top-level E1 state is authoritative")
    trace.append("V9_CONSISTENCY -> trend_state, directional_pressure and market_state reconciled")
    trace.append("V9_PHASE_BOUNDARY -> counter-pressure/pullback cannot independently reverse regime")
    output["reasoning_trace"] = list(dict.fromkeys(trace))

    reasons = list(output.get("reasons") or [])
    reasons.extend(("V9_AUTHORITATIVE_E1_TELEMETRY", "V9_STATE_CONSISTENCY_CONTRACT"))
    output["reasons"] = list(dict.fromkeys(str(x) for x in reasons))
    return output
