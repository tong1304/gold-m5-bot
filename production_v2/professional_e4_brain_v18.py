"""Production-V2 E4 Professional Liquidity & Auction Brain v18.

This layer hardens the E4 decision model without changing E1/E2/E3.  It keeps
E4 analysis-only and makes the auction read explicit: liquidity event, taker,
reaction/acceptance, post-event displacement, competing interpretation, and
confidence.  E9 remains the only trade-decision authority.
"""
from __future__ import annotations

from math import isfinite
from typing import Any

from .professional_e4_brain_v15 import analyze_e4 as _analyze_e4_v17

PROFESSIONAL_QUESTION = "Where is liquidity, who took it, and did price accept or reject the auction?"
E4_ROLE = "LIQUIDITY_AUCTION_ANALYST"
ARCHITECTURE = "E4_SINGLE_PROFESSIONAL_BRAIN_V18"


def _num(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def _valid_bars(snapshot: Any) -> list[dict[str, float]]:
    raw = snapshot.get("bars", []) if isinstance(snapshot, dict) else snapshot
    result = []
    for bar in raw if isinstance(raw, (list, tuple)) else []:
        if not isinstance(bar, dict):
            continue
        values = {key: _num(bar.get(key)) for key in ("open", "high", "low", "close")}
        if all(value is not None for value in values.values()):
            result.append(values)
    return result


def _displacement(event: dict[str, Any], bars: list[dict[str, float]], atr: float) -> dict[str, Any]:
    index = int(event.get("index", -1))
    direction = str(event.get("directional_implication") or "NEUTRAL").upper()
    if index < 0 or index >= len(bars) - 1 or atr <= 0:
        return {"observed": False, "direction": direction, "atr_multiple": 0.0, "bars": 0}
    origin = float(bars[index]["close"])
    closes = [float(bar["close"]) for bar in bars[index + 1:index + 4]]
    if not closes:
        return {"observed": False, "direction": direction, "atr_multiple": 0.0, "bars": 0}
    if direction == "UP":
        move = max(closes) - origin
    elif direction == "DOWN":
        move = origin - min(closes)
    else:
        move = 0.0
    return {
        "observed": move > 0,
        "direction": direction,
        "atr_multiple": round(max(move, 0.0) / atr, 3),
        "bars": len(closes),
    }


def _quality(event: dict[str, Any], auction: dict[str, Any], displacement: dict[str, Any]) -> dict[str, Any]:
    state = str(auction.get("state") or "UNRESOLVED")
    confirmed = bool(auction.get("confirmed"))
    zone = event.get("zone") or {}
    touches = int(zone.get("touches", 1) or 1)
    event_strength = float(event.get("strength", 0.0) or 0.0)
    if confirmed and state == "REJECTION_CONFIRMED":
        classification = "HIGH_CONVICTION_REJECTION" if touches >= 2 and event_strength >= 0.9 and displacement.get("observed") else "CONFIRMED_REJECTION"
    elif confirmed and state == "ACCEPTANCE_CONFIRMED":
        classification = "HIGH_CONVICTION_ACCEPTANCE" if touches >= 2 and event_strength >= 0.85 and displacement.get("observed") else "CONFIRMED_ACCEPTANCE"
    elif state in {"REJECTION_PENDING", "ACCEPTANCE_PENDING", "INVALIDATED"}:
        classification = "PENDING_OR_INVALIDATED"
    else:
        classification = "UNRESOLVED"
    return {
        "classification": classification,
        "confirmed": confirmed,
        "zone_touches": touches,
        "event_strength": round(event_strength, 3),
        "follow_through_bars": int(auction.get("follow_through_bars", 0) or 0),
        "displacement_observed": bool(displacement.get("observed")),
    }


def _competing_interpretations(event: dict[str, Any], auction: dict[str, Any]) -> list[str]:
    kind = str(event.get("type") or "NO_CONFIRMED_LIQUIDITY_EVENT")
    state = str(auction.get("state") or "UNRESOLVED")
    if not event.get("zone"):
        return ["NO_LIQUIDITY_EVENT"]
    if state == "INVALIDATED":
        return ["POST_EVENT_RECLAMATION", "ORIGINAL_AUCTION_THESIS_REJECTED"]
    if "REJECTION" in kind or "FAILED_BREAK" in kind:
        return ["LIQUIDITY_TAKEN_AND_REJECTED", "TRUE_ACCEPTANCE_REMAINS_POSSIBLE_UNTIL_RECLAIM_FAILS"] if state != "REJECTION_CONFIRMED" else ["CONFIRMED_REJECTION", "CONTINUATION_REQUIRES_DOWNSTREAM_CONFIRMATION"]
    if "ACCEPTANCE" in kind:
        return ["LIQUIDITY_TAKEN_AND_ACCEPTED", "FAILED_BREAK_RECLAIM_REMAINS_POSSIBLE_UNTIL_FOLLOW_THROUGH_CONFIRMS"] if state != "ACCEPTANCE_CONFIRMED" else ["CONFIRMED_ACCEPTANCE", "CONTINUATION_REQUIRES_DOWNSTREAM_CONFIRMATION"]
    return ["LIQUIDITY_INTERACTION", "AUCTION_DIRECTION_UNRESOLVED"]


def _professional_reasoning(result: dict[str, Any]) -> list[str]:
    event = result.get("event") or {}
    auction = result.get("auction") or {}
    quality = result.get("auction_quality") or {}
    displacement = result.get("post_event_displacement") or {}
    return [
        f"liquidity_event={event.get('type', 'NONE')}",
        f"liquidity_taker={event.get('liquidity_taker', 'NONE')}",
        f"auction_state={auction.get('state', 'UNRESOLVED')}",
        f"auction_confirmed={bool(auction.get('confirmed'))}",
        f"event_quality={quality.get('classification', 'UNRESOLVED')}",
        f"post_event_displacement_atr={displacement.get('atr_multiple', 0.0)}",
        "E4 provides evidence only; no trade decision or gate is issued.",
    ]


def analyze_e4(snapshot=None, evidence_bus=None):
    result = dict(_analyze_e4_v17(snapshot, evidence_bus))
    bars = _valid_bars(snapshot or {})
    event = dict(result.get("event") or {})
    auction = dict(result.get("auction") or {})
    atr = 0.0
    observations = result.get("observations") or []
    for item in observations:
        if str(item).startswith("atr14="):
            atr = _num(str(item).split("=", 1)[1]) or 0.0
            break
    displacement = _displacement(event, bars, atr)
    quality = _quality(event, auction, displacement)
    result.update({
        "architecture": ARCHITECTURE,
        "professional_brain": True,
        "role": E4_ROLE,
        "question": PROFESSIONAL_QUESTION,
        "auction_quality": quality,
        "event_quality": quality["classification"],
        "post_event_displacement": displacement,
        "competing_interpretations": _competing_interpretations(event, auction),
        "liquidity_taker_confidence": "HIGH" if event.get("zone") and float(event.get("strength", 0.0) or 0.0) >= 0.85 else "MEDIUM" if event.get("zone") else "LOW",
        "professional_reasoning": [],
        "decision": None,
        "gate": None,
        "score": None,
        "trade_decision_authority": False,
        "decision_authority": "E9_ONLY",
        "reasoning_role": E4_ROLE,
        "upstream_decisions_used": False,
        "upstream_gates_used": False,
        "score_used": False,
    })
    result["professional_reasoning"] = _professional_reasoning(result)
    return result
