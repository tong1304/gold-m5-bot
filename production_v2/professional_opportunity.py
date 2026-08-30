from __future__ import annotations

"""Cross-engine opportunity radar.

This module does not create trades. It translates each brain's existing evidence
into a stable opportunity lifecycle so a real edge can remain visible while
execution is correctly blocked by proof, location, or economics.
"""

from typing import Any

DIRECTIONS = {"BUY", "SELL"}


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(f"{k}={_text(v)}" for k, v in sorted(value.items(), key=lambda x: str(x[0])))
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(v) for v in value)
    return str(value if value is not None else "").upper().strip()


def _direction(output: dict[str, Any]) -> str:
    direct = output.get("direction")
    if _text(direct) in DIRECTIONS:
        return _text(direct)
    for key in ("structure_direction", "market_direction", "bos_direction", "pressure", "long_horizon_direction", "repricing_direction"):
        value = _text(output.get(key))
        if value in {"UP", "BULLISH", "TREND_UP", "BUY"}:
            return "BUY"
        if value in {"DOWN", "BEARISH", "TREND_DOWN", "SELL"}:
            return "SELL"
    text = _text(output.get("finding"))
    if text.startswith("BUY ") or "PRESSURE=UP" in text or "STRUCTURE=BULLISH" in text:
        return "BUY"
    if text.startswith("SELL ") or "PRESSURE=DOWN" in text or "STRUCTURE=BEARISH" in text:
        return "SELL"
    return "NEUTRAL"


def _codes(output: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("reason_codes", "reasons", "counter_evidence", "blockers", "conflicts", "invalidations", "vetoes", "hard_veto", "secondary_blockers"):
        value = output.get(key)
        if isinstance(value, str):
            values.append(_text(value))
        elif isinstance(value, dict):
            for k, v in value.items():
                if v is True:
                    values.append(_text(k))
                elif v not in (None, False, ""):
                    values.append(_text(v))
        elif isinstance(value, (list, tuple, set)):
            values.extend(_text(v) for v in value if v is not None)
    return list(dict.fromkeys(v for v in values if v))


def _num(output: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        try:
            x = float(output.get(key))
        except (TypeError, ValueError):
            continue
        if x == x and abs(x) != float("inf"):
            return x
    return None


def _space(output: dict[str, Any], direction: str) -> float | None:
    keys = ("available_space_atr_long", "long_space_atr", "effective_space_atr", "space_atr") if direction == "BUY" else ("available_space_atr_short", "short_space_atr", "effective_space_atr", "space_atr") if direction == "SELL" else ("effective_space_atr", "space_atr")
    return _num(output, *keys)


def _stage(engine: str, direction: str, output: dict[str, Any], codes: list[str]) -> str:
    text = " ".join(codes)
    state = _text(output.get("state") or output.get("finding") or output.get("lifecycle"))
    if any(x in text or x in state for x in ("INVALIDATED", "NO_OPPORTUNITY")):
        return "INVALIDATED"
    if engine == "E1":
        return "STATE_ESTABLISHED" if direction in DIRECTIONS and state not in {"UNCLEAR", "UNKNOWN"} else "STATE_WATCH"
    if engine == "E2":
        maturity = _text(output.get("opportunity_maturity"))
        if maturity in {"ACTIONABLE", "CONFIRMED"}:
            return "REGIME_CONFIRMED"
        return "REGIME_DEVELOPING" if direction in DIRECTIONS else "REGIME_UNRESOLVED"
    if engine == "E3":
        lifecycle = _text(output.get("lifecycle") or output.get("structure_lifecycle"))
        if lifecycle in {"ESTABLISHED", "CONFIRMED", "BOS_UP", "BOS_DOWN", "CHOCH"}:
            return "STRUCTURE_ESTABLISHED"
        return "STRUCTURE_FORMING" if direction in DIRECTIONS else "STRUCTURE_WATCH"
    if engine == "E4":
        auction = _text(output.get("auction_state") or output.get("auction_phase"))
        if auction in {"CONFIRMED", "ACCEPTED", "REJECTED"}:
            return "AUCTION_CONFIRMED"
        return "AUCTION_PENDING" if direction in DIRECTIONS else "AUCTION_WATCH"
    if engine == "E5":
        return "LOCATION_ACTIONABLE" if direction in DIRECTIONS and not any(x in text for x in ("SPACE_CONSTRAINED", "NO_REVERSAL_EDGE")) else "LOCATION_ASSESSED"
    if engine == "E6":
        if any(x in text for x in ("SETUP_CONFIRMED", "TRADE_READY")):
            return "SETUP_MATURE"
        return "SETUP_VALIDATING" if direction in DIRECTIONS else "SETUP_WATCH"
    if engine == "E7":
        confirmation = _text(output.get("confirmation_state"))
        return "CONFIRMED" if confirmation in {"PROVEN", "CONFIRMED"} else "WAITING_CONFIRMATION" if direction in DIRECTIONS else "CONFIRMATION_WATCH"
    if engine == "E8":
        if any(x in text for x in ("INVALID_TRADE_GEOMETRY", "NO_USABLE_STRUCTURAL_TARGET", "REAL_RR_BELOW_MINIMUM", "STOP_TOO_WIDE", "TARGET_REALISM_TOO_LOW")):
            return "ECONOMICALLY_BLOCKED"
        return "ECONOMICALLY_VALIDATED" if direction in DIRECTIONS else "ECONOMIC_WATCH"
    return "EXECUTABLE" if _text(output.get("decision")) in DIRECTIONS and bool(output.get("gate_passed")) else "CONTROLLED_WAIT"


def enrich_engine(engine: str, output: dict[str, Any], upstream: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    out = dict(output or {})
    direction = _direction(out)
    codes = _codes(out)
    stage = _stage(engine, direction, out, codes)
    space = _space(out, direction)
    confidence = _num(out, "confidence", "evidence_strength", "quality", "opportunity_score")
    if confidence is None:
        confidence = 0.0
    if confidence > 1.0:
        confidence /= 100.0
    confidence = max(0.0, min(1.0, confidence))

    visible = direction in DIRECTIONS and stage not in {"INVALIDATED", "STATE_WATCH", "REGIME_UNRESOLVED", "STRUCTURE_WATCH", "AUCTION_WATCH", "SETUP_WATCH", "CONFIRMATION_WATCH", "ECONOMIC_WATCH"}
    pending = stage in {"REGIME_DEVELOPING", "STRUCTURE_FORMING", "AUCTION_PENDING", "SETUP_VALIDATING", "WAITING_CONFIRMATION", "ECONOMICALLY_BLOCKED", "LOCATION_ASSESSED", "CONTROLLED_WAIT"}
    if not visible and direction in DIRECTIONS and pending:
        visible = True

    space_quality = None if space is None else max(0.0, min(100.0, space / 2.0 * 100.0))
    counter = [c for c in codes if any(x in c for x in ("CONFLICT", "MISSING", "PENDING", "BLOCK", "RISK", "CONSTRAINED", "UNRESOLVED"))]
    opportunity_state = "NO_OPPORTUNITY" if direction == "NEUTRAL" else "OPPORTUNITY_WAITING" if pending else "OPPORTUNITY_VISIBLE" if visible else "NO_OPPORTUNITY"

    next_event = {
        "E1": "NEXT_CLOSED_CANDLE_REGIME_UPDATE",
        "E2": "AUCTION_ACCEPTANCE_OR_FOLLOW_THROUGH",
        "E3": "BOS_CHOCH_OR_PROTECTED_LEVEL_REACTION",
        "E4": "AUCTION_FOLLOW_THROUGH_OR_REJECTION",
        "E5": "PRICE_RESPONSE_AT_VALUE_OR_TARGET_SPACE_OPENING",
        "E6": "SETUP_SPECIFIC_CONFIRMATION",
        "E7": "VALID_CLOSED_CANDLE_TRIGGER_OR_INVALIDATION",
        "E8": "SURVIVABLE_GEOMETRY_AND_REALISTIC_TARGET",
        "E9": "ALL_CONTROL_GATES_PASS",
    }[engine]

    score = 100.0 * confidence
    if space_quality is not None:
        score = 0.65 * score + 0.35 * space_quality
    score = round(max(0.0, min(100.0, score - min(30.0, len(counter) * 5.0))), 2)

    out["professional_opportunity"] = {
        "engine": engine,
        "direction": direction,
        "state": opportunity_state,
        "stage": stage,
        "score": score,
        "evidence_quality": round(confidence * 100.0, 2),
        "space_atr": space,
        "space_quality": space_quality,
        "observed_evidence": codes,
        "counter_evidence": counter,
        "next_required_event": next_event,
        "trade_authorized": engine == "E9" and _text(out.get("decision")) in DIRECTIONS and bool(out.get("gate_passed")),
        "authority": engine,
    }
    out["opportunity_state"] = opportunity_state
    out["opportunity_stage"] = stage
    out["opportunity_direction"] = direction
    out["opportunity_next_event"] = next_event
    out["opportunity_score"] = score
    return out


def consolidate(results: dict[str, Any]) -> dict[str, Any]:
    radar = []
    for engine in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"):
        result = results.get(engine)
        if not result:
            continue
        output = result.output if hasattr(result, "output") else result
        op = output.get("professional_opportunity") or {}
        if op.get("state") != "NO_OPPORTUNITY":
            radar.append({"engine": engine, "direction": op.get("direction"), "state": op.get("state"), "stage": op.get("stage"), "score": op.get("score"), "next_required_event": op.get("next_required_event")})
    radar.sort(key=lambda x: (x.get("state") == "OPPORTUNITY_VISIBLE", x.get("score", 0.0)), reverse=True)
    return {"count": len(radar), "candidates": radar, "best": radar[0] if radar else None}
