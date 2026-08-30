"""Cross-engine professional opportunity visibility layer.

This module does not loosen execution gates. It makes each engine explicitly
state the opportunity it can see, the evidence supporting it, the constraints,
and the next event required before the next engine may promote it.
"""
from __future__ import annotations

from typing import Any


DIRECTIONS = {"BUY", "SELL", "NEUTRAL"}


def _text(output: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = output.get(key)
        if value is not None:
            return str(value).upper()
    return ""


def _num(output: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        try:
            value = float(output.get(key))
        except (TypeError, ValueError):
            continue
        return value
    return None


def _base(engine_id: str) -> dict[str, Any]:
    return {
        "professional_opportunity": True,
        "opportunity_engine": engine_id,
        "opportunity_direction": "NEUTRAL",
        "opportunity_state": "WATCH",
        "opportunity_stage": "OBSERVE",
        "opportunity_score": 0.0,
        "opportunity_evidence": [],
        "opportunity_constraints": [],
        "opportunity_next_event": "NEXT_CLOSED_M5_CANDLE",
        "entry_authorized": False,
        "trade_authorized": False,
    }


def enrich_professional_opportunity(engine_id: str, output: dict[str, Any], snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Expose opportunity intelligence while preserving every engine boundary."""
    out = dict(output or {})
    result = _base(engine_id)
    result["opportunity_direction"] = _text(out, "direction", "opportunity_direction") if _text(out, "direction", "opportunity_direction") in DIRECTIONS else "NEUTRAL"

    finding = _text(out, "finding", "state", "market_state")
    reason_text = " ".join(str(x).upper() for x in (out.get("reasons") or out.get("reason_codes") or []))
    evidence = result["opportunity_evidence"]
    constraints = result["opportunity_constraints"]

    if engine_id == "E1":
        state = _text(out, "state", "market_state")
        direction = "BUY" if state == "TREND_UP" else "SELL" if state == "TREND_DOWN" else "BUY" if _text(out, "direction") == "UP" else "SELL" if _text(out, "direction") == "DOWN" else "NEUTRAL"
        result.update({"opportunity_direction": direction, "opportunity_state": "DEVELOPING" if state in {"TREND_UP", "TREND_DOWN"} else "WATCH", "opportunity_stage": "MARKET_STATE"})
        evidence.append(f"MARKET_STATE={state or 'UNRESOLVED'}")
        if _text(out, "structure") in {"BULLISH", "BEARISH"}:
            evidence.append(f"STRUCTURE={_text(out, 'structure')}")
        if state in {"TRANSITION", "RANGE", "UNCLEAR"}:
            constraints.append(f"REGIME={state}")
        result["opportunity_next_event"] = "CLOSED_CANDLE_CONFIRMATION_IN_DIRECTION" if direction != "NEUTRAL" else "REGIME_RESOLUTION"

    elif engine_id == "E2":
        candidates = out.get("candidate_hypotheses") or []
        if candidates:
            best = next((c for c in candidates if isinstance(c, dict) and c.get("direction") in DIRECTIONS), None)
            if best:
                result["opportunity_direction"] = "BUY" if str(best.get("direction")).upper() == "UP" else "SELL" if str(best.get("direction")).upper() == "DOWN" else str(best.get("direction")).upper()
                result["opportunity_score"] = float(best.get("evidence_score", best.get("quality", 0.0)) or 0.0)
                result["opportunity_state"] = "CONDITIONAL" if not best.get("eligible") else "DEVELOPING"
                result["opportunity_stage"] = "OPPORTUNITY_MAP"
                evidence.append(f"CANDIDATE={best.get('name', 'UNKNOWN')}")
                constraints.extend(str(v) for v in (best.get("vetoes") or []))
        if not candidates and "DIRECTIONAL" in reason_text:
            result["opportunity_state"] = "WATCH"
            evidence.append("DIRECTIONAL_EVIDENCE_PRESENT")
        result["opportunity_next_event"] = "CLOSED_CANDLE_ACCEPTANCE_AND_FOLLOW_THROUGH"

    elif engine_id == "E3":
        state = _text(out, "finding", "state", "lifecycle")
        bos = _text(out, "bos", "external_bos", "event")
        direction = _text(out, "direction", "bos_direction")
        if direction == "UP": result["opportunity_direction"] = "BUY"
        elif direction == "DOWN": result["opportunity_direction"] = "SELL"
        result["opportunity_state"] = "DEVELOPING" if bos not in {"", "NO_BREAK", "NO_BOS"} else "WATCH"
        result["opportunity_stage"] = "STRUCTURE"
        evidence.append(f"STRUCTURE={state or 'UNRESOLVED'}")
        if bos in {"NO_BREAK", "NO_BOS"} or "TRANSITION" in state:
            constraints.append("STRUCTURE_NOT_RESOLVED")
        result["opportunity_next_event"] = "CONFIRMED_BOS_OR_STRUCTURE_RECLAIM"

    elif engine_id == "E4":
        if "SWEEP_REJECTION" in finding or "FAILED" in finding or "REJECTION" in finding:
            result["opportunity_direction"] = "SELL" if "HIGH" in finding or "SELL" in reason_text else "BUY"
            result["opportunity_state"] = "CONDITIONAL"
            result["opportunity_stage"] = "AUCTION_REJECTION"
            evidence.append(f"AUCTION={finding}")
            result["opportunity_next_event"] = "CLOSED_CANDLE_RECLAIM_AND_FOLLOW_THROUGH"
            if _text(out, "auction_state") == "PENDING": constraints.append("AUCTION_CONFIRMATION_PENDING")
        elif "ACCEPTANCE" in finding:
            result["opportunity_direction"] = "BUY" if "HIGH" in finding or "BUY" in finding else "SELL"
            result["opportunity_state"] = "CONDITIONAL"
            result["opportunity_stage"] = "AUCTION_ACCEPTANCE"
            evidence.append(f"AUCTION={finding}")
            result["opportunity_next_event"] = "ACCEPTANCE_FOLLOW_THROUGH"
        else:
            result["opportunity_next_event"] = "NEW_LIQUIDITY_EVENT"

    elif engine_id == "E5":
        value_state = _text(out, "value_state")
        location = _text(out, "structural_location", "location")
        long_space = _num(out, "available_space_atr_long")
        short_space = _num(out, "available_space_atr_short")
        if value_state == "PREMIUM" and ("RESISTANCE" in location or (short_space is not None and long_space is not None and short_space > long_space)):
            result["opportunity_direction"] = "SELL"
            result["opportunity_state"] = "CONDITIONAL"
            result["opportunity_stage"] = "LOCATION_EDGE"
            evidence.append("PREMIUM_LOCATION")
        elif value_state == "DISCOUNT":
            result["opportunity_direction"] = "BUY"
            result["opportunity_state"] = "CONDITIONAL"
            result["opportunity_stage"] = "LOCATION_EDGE"
            evidence.append("DISCOUNT_LOCATION")
        if long_space is not None and long_space < 1.0: constraints.append("LONG_SPACE_CONSTRAINED")
        if short_space is not None and short_space < 1.0: constraints.append("SHORT_SPACE_CONSTRAINED")
        result["opportunity_next_event"] = "FRESH_LIQUIDITY_CONFIRMATION_AT_ADVANTAGEOUS_LOCATION"

    elif engine_id == "E6":
        direction = _text(out, "direction")
        if direction == "UP": result["opportunity_direction"] = "BUY"
        elif direction == "DOWN": result["opportunity_direction"] = "SELL"
        elif "BUY" in finding: result["opportunity_direction"] = "BUY"
        elif "SELL" in finding: result["opportunity_direction"] = "SELL"
        result["opportunity_state"] = "DEVELOPING" if "validating" in finding.lower() else "WATCH"
        result["opportunity_stage"] = "SETUP_FORMATION"
        evidence.append(f"SETUP={finding or 'UNRESOLVED'}")
        constraints.extend(x for x in ("SPACE_CONFLICT", "STRUCTURE_CONFLICT", "DIRECTIONAL_EVIDENCE_CONFLICT") if x in reason_text)
        result["opportunity_next_event"] = "SETUP_SPECIFIC_CLOSED_CANDLE_TRIGGER"

    elif engine_id == "E7":
        direction = _text(out, "direction", "opportunity_direction")
        if direction in DIRECTIONS: result["opportunity_direction"] = direction
        result["opportunity_stage"] = "CONFIRMATION"
        missing = out.get("missing_evidence") or []
        result["opportunity_state"] = "CONDITIONAL" if missing else "DEVELOPING"
        evidence.extend(str(x) for x in missing[:5])
        result["opportunity_next_event"] = "VALID_CLOSED_CANDLE_TRIGGER"
        if missing: constraints.append("PROOF_GATES_INCOMPLETE")

    elif engine_id == "E8":
        result["opportunity_stage"] = "TRADE_ECONOMICS"
        result["opportunity_state"] = "CONDITIONAL"
        direction = _text(out, "direction", "opportunity_direction")
        if direction in DIRECTIONS: result["opportunity_direction"] = direction
        reasons = out.get("reasons") or out.get("reason_codes") or []
        constraints.extend(str(x) for x in reasons[:8])
        result["opportunity_next_event"] = "VALID_TRADE_GEOMETRY_AND_STRUCTURAL_TARGET"

    elif engine_id == "E9":
        decision = _text(out, "decision")
        direction = decision if decision in {"BUY", "SELL"} else _text(out, "direction", "opportunity_direction")
        if direction in DIRECTIONS: result["opportunity_direction"] = direction
        execution = _text(out, "execution")
        setup = _text(out, "setup")
        if decision in {"BUY", "SELL"} and execution not in {"BLOCKED", "NO_TRADE"}:
            result["opportunity_state"] = "DEVELOPING"
        elif setup in {"VALIDATING", "ESTABLISHED"}:
            result["opportunity_state"] = "CONDITIONAL"
        else:
            result["opportunity_state"] = "BLOCKED"
        result["opportunity_stage"] = "MASTER_CONTROL"
        result["entry_authorized"] = False
        result["trade_authorized"] = False
        result["opportunity_next_event"] = "NEXT_CLOSED_M5_CANDLE"
        evidence.append("MASTER_CONTROL_RETAINS_EXECUTION_AUTHORITY")

    if result["opportunity_direction"] == "NEUTRAL":
        result["opportunity_state"] = "WATCH"
    result["opportunity_score"] = round(max(0.0, min(1.0, float(result["opportunity_score"] or out.get("confidence", 0.0) or 0.0))), 3)
    result["opportunity_constraints"] = list(dict.fromkeys(constraints))
    result["opportunity_evidence"] = list(dict.fromkeys(evidence))
    out.update(result)
    return out
