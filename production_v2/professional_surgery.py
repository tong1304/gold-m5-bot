"""Cross-engine professional opportunity visibility layer.

This module is deliberately non-authoritative. It adds a second, auditable
opportunity lens to each engine without replacing the existing professional
opportunity contract or changing execution gates.
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
    return {"engine": engine_id, "direction": "NEUTRAL", "state": "WATCH", "stage": "OBSERVE", "score": 0.0, "evidence": [], "constraints": [], "next_required_event": "NEXT_CLOSED_M5_CANDLE", "entry_authorized": False, "trade_authorized": False}


def enrich_professional_opportunity(engine_id: str, output: dict[str, Any], snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Expose a scoped opportunity lens while preserving existing contracts."""
    del snapshot
    out = dict(output or {})
    result = _base(engine_id)
    finding = _text(out, "finding", "state", "market_state")
    reason_text = " ".join(str(x).upper() for x in (out.get("reasons") or out.get("reason_codes") or []))
    evidence, constraints = result["evidence"], result["constraints"]

    if engine_id == "E1":
        state = _text(out, "state", "market_state")
        direction = "BUY" if state == "TREND_UP" else "SELL" if state == "TREND_DOWN" else "BUY" if _text(out, "direction") == "UP" else "SELL" if _text(out, "direction") == "DOWN" else "NEUTRAL"
        result.update(direction=direction, state="DEVELOPING" if state in {"TREND_UP", "TREND_DOWN"} else "WATCH", stage="MARKET_STATE")
        evidence.append(f"MARKET_STATE={state or 'UNRESOLVED'}")
        if _text(out, "structure") in {"BULLISH", "BEARISH"}: evidence.append(f"STRUCTURE={_text(out, 'structure')}")
        if state in {"TRANSITION", "RANGE", "UNCLEAR"}: constraints.append(f"REGIME={state}")
        result["next_required_event"] = "CLOSED_CANDLE_CONFIRMATION_IN_DIRECTION" if direction != "NEUTRAL" else "REGIME_RESOLUTION"

    elif engine_id == "E2":
        candidates = out.get("candidate_hypotheses") or []
        if candidates:
            best = next((c for c in candidates if isinstance(c, dict)), None)
            if best:
                raw = str(best.get("direction", "")).upper()
                result["direction"] = "BUY" if raw == "UP" else "SELL" if raw == "DOWN" else raw if raw in DIRECTIONS else "NEUTRAL"
                result["score"] = float(best.get("evidence_score", best.get("quality", 0.0)) or 0.0)
                result["state"] = "CONDITIONAL" if not best.get("eligible") else "DEVELOPING"
                result["stage"] = "OPPORTUNITY_MAP"
                evidence.append(f"CANDIDATE={best.get('name', 'UNKNOWN')}")
                constraints.extend(str(v) for v in (best.get("vetoes") or []))
        elif "DIRECTIONAL" in reason_text: evidence.append("DIRECTIONAL_EVIDENCE_PRESENT")
        result["next_required_event"] = "CLOSED_CANDLE_ACCEPTANCE_AND_FOLLOW_THROUGH"

    elif engine_id == "E3":
        state = _text(out, "finding", "state", "lifecycle")
        bos = _text(out, "bos", "external_bos", "event")
        direction = _text(out, "direction", "bos_direction")
        if direction == "UP": result["direction"] = "BUY"
        elif direction == "DOWN": result["direction"] = "SELL"
        result["state"] = "DEVELOPING" if bos not in {"", "NO_BREAK", "NO_BOS"} else "WATCH"
        result["stage"] = "STRUCTURE"
        evidence.append(f"STRUCTURE={state or 'UNRESOLVED'}")
        if bos in {"NO_BREAK", "NO_BOS"} or "TRANSITION" in state: constraints.append("STRUCTURE_NOT_RESOLVED")
        result["next_required_event"] = "CONFIRMED_BOS_OR_STRUCTURE_RECLAIM"

    elif engine_id == "E4":
        if "SWEEP_REJECTION" in finding or "FAILED" in finding or "REJECTION" in finding:
            result.update(direction="SELL" if "HIGH" in finding or "SELL" in reason_text else "BUY", state="CONDITIONAL", stage="AUCTION_REJECTION")
            evidence.append(f"AUCTION={finding}")
            result["next_required_event"] = "CLOSED_CANDLE_RECLAIM_AND_FOLLOW_THROUGH"
            if _text(out, "auction_state") == "PENDING": constraints.append("AUCTION_CONFIRMATION_PENDING")
        elif "ACCEPTANCE" in finding:
            result.update(direction="BUY" if "HIGH" in finding or "BUY" in finding else "SELL", state="CONDITIONAL", stage="AUCTION_ACCEPTANCE")
            evidence.append(f"AUCTION={finding}")
            result["next_required_event"] = "ACCEPTANCE_FOLLOW_THROUGH"
        else: result["next_required_event"] = "NEW_LIQUIDITY_EVENT"

    elif engine_id == "E5":
        value_state = _text(out, "value_state")
        location = _text(out, "structural_location", "location")
        long_space, short_space = _num(out, "available_space_atr_long"), _num(out, "available_space_atr_short")
        if value_state == "PREMIUM" and ("RESISTANCE" in location or (short_space is not None and long_space is not None and short_space > long_space)):
            result.update(direction="SELL", state="CONDITIONAL", stage="LOCATION_EDGE"); evidence.append("PREMIUM_LOCATION")
        elif value_state == "DISCOUNT":
            result.update(direction="BUY", state="CONDITIONAL", stage="LOCATION_EDGE"); evidence.append("DISCOUNT_LOCATION")
        if long_space is not None and long_space < 1.0: constraints.append("LONG_SPACE_CONSTRAINED")
        if short_space is not None and short_space < 1.0: constraints.append("SHORT_SPACE_CONSTRAINED")
        result["next_required_event"] = "FRESH_LIQUIDITY_CONFIRMATION_AT_ADVANTAGEOUS_LOCATION"

    elif engine_id == "E6":
        direction = _text(out, "direction")
        if direction == "UP": result["direction"] = "BUY"
        elif direction == "DOWN": result["direction"] = "SELL"
        elif "BUY" in finding: result["direction"] = "BUY"
        elif "SELL" in finding: result["direction"] = "SELL"
        result.update(state="DEVELOPING" if "VALIDATING" in finding else "WATCH", stage="SETUP_FORMATION")
        evidence.append(f"SETUP={finding or 'UNRESOLVED'}")
        constraints.extend(x for x in ("SPACE_CONFLICT", "STRUCTURE_CONFLICT", "DIRECTIONAL_EVIDENCE_CONFLICT") if x in reason_text)
        result["next_required_event"] = "SETUP_SPECIFIC_CLOSED_CANDLE_TRIGGER"

    elif engine_id == "E7":
        direction = _text(out, "direction", "opportunity_direction")
        if direction in DIRECTIONS: result["direction"] = direction
        result["stage"] = "CONFIRMATION"
        missing = out.get("missing_evidence") or []
        result["state"] = "CONDITIONAL" if missing else "DEVELOPING"
        evidence.extend(str(x) for x in missing[:5])
        result["next_required_event"] = "VALID_CLOSED_CANDLE_TRIGGER"
        if missing: constraints.append("PROOF_GATES_INCOMPLETE")

    elif engine_id == "E8":
        result.update(stage="TRADE_ECONOMICS", state="CONDITIONAL")
        direction = _text(out, "direction", "opportunity_direction")
        if direction in DIRECTIONS: result["direction"] = direction
        constraints.extend(str(x) for x in (out.get("reasons") or out.get("reason_codes") or [])[:8])
        result["next_required_event"] = "VALID_TRADE_GEOMETRY_AND_STRUCTURAL_TARGET"

    elif engine_id == "E9":
        decision = _text(out, "decision")
        direction = decision if decision in {"BUY", "SELL"} else _text(out, "direction", "opportunity_direction")
        if direction in DIRECTIONS: result["direction"] = direction
        setup, execution = _text(out, "setup"), _text(out, "execution")
        result["state"] = "DEVELOPING" if decision in {"BUY", "SELL"} and execution not in {"BLOCKED", "NO_TRADE"} else "CONDITIONAL" if setup in {"VALIDATING", "ESTABLISHED"} else "BLOCKED"
        result["stage"] = "MASTER_CONTROL"
        result["entry_authorized"] = False
        result["trade_authorized"] = False
        result["next_required_event"] = "NEXT_CLOSED_M5_CANDLE"
        evidence.append("MASTER_CONTROL_RETAINS_EXECUTION_AUTHORITY")

    if result["direction"] == "NEUTRAL": result["state"] = "WATCH"
    result["score"] = round(max(0.0, min(1.0, float(result["score"] or out.get("confidence", 0.0) or 0.0))), 3)
    result["constraints"] = list(dict.fromkeys(constraints))
    result["evidence"] = list(dict.fromkeys(evidence))
    out["professional_surgery"] = result
    return out
