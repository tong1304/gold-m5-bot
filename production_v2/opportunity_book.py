from __future__ import annotations

from typing import Any

VALID_DIRECTIONS = {"BUY", "SELL"}
TERMINAL = {"INVALIDATED", "EXPIRED", "REPLACED", "EXECUTED"}


def _direction(value: Any) -> str:
    return str(value or "").upper().strip()


def _quality(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    if number != number:
        number = 0.0
    return max(0.0, min(1.0, number))


def build_candidate(
    direction: Any,
    family: Any,
    origin_candle: Any,
    quality: Any = 0.0,
    **evidence: Any,
) -> dict[str, Any]:
    direction = _direction(direction)
    if direction not in VALID_DIRECTIONS:
        raise ValueError("direction must be BUY or SELL")

    return {
        "direction": direction,
        "family": str(family or "").upper().strip(),
        "origin_candle": origin_candle,
        "quality": _quality(quality),
        "state": str(evidence.get("state") or "FORMING").upper().strip(),
        "wait_for": list(evidence.get("wait_for") or []),
        "causal_evidence": dict(evidence.get("causal_evidence") or {}),
        "invalidation_conditions": list(evidence.get("invalidation_conditions") or []),
    }


def compare_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    active = [c for c in candidates if str(c.get("state") or "").upper() not in TERMINAL]
    ranked = sorted(active, key=lambda c: _quality(c.get("quality")), reverse=True)
    directions = {str(c.get("direction") or "").upper().strip() for c in active}
    directions.discard("")

    if not ranked:
        leader = "NEUTRAL"
    else:
        leader = str(ranked[0].get("direction") or "NEUTRAL").upper().strip()

    return {
        "leader": leader,
        "competition": "CONTESTED" if directions == {"BUY", "SELL"} else "UNCONTESTED",
        "ranked": ranked,
    }


def update_book(
    previous: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    previous = dict(previous or {})
    merged = [dict(candidate) for candidate in (previous.get("candidates") or [])]

    for candidate in candidates:
        candidate = dict(candidate)
        direction = _direction(candidate.get("direction"))
        family = str(candidate.get("family") or "").upper().strip()
        origin = candidate.get("origin_candle")
        replaced = False
        for index, existing in enumerate(merged):
            if (
                _direction(existing.get("direction")) == direction
                and str(existing.get("family") or "").upper().strip() == family
                and existing.get("origin_candle") == origin
            ):
                merged[index] = candidate
                replaced = True
                break
        if not replaced:
            merged.append(candidate)

    comparison = compare_candidates(merged)
    return {
        "candidates": merged,
        "leader": comparison["leader"],
        "competition": comparison["competition"],
        "ranked": comparison["ranked"],
    }
