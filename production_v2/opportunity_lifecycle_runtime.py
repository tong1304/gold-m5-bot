from __future__ import annotations

"""Runtime boundary for directional opportunity lifecycle observability.

The pipeline remains the canonical lifecycle authority. This boundary only
corrects event attribution for counter-direction watches and emits a compact
radar log; it never authorizes execution.
"""

import logging
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger(__name__)
_TERMINAL = {"INVALIDATED", "EXPIRED", "REPLACED", "EXECUTED"}


def _direction(value: Any) -> str:
    text = str(value or "").upper().strip()
    if text in {"UP", "BULLISH", "TREND_UP", "BUY"} or text.startswith(("BUY ", "BUY_", "BUY:")):
        return "BUY"
    if text in {"DOWN", "BEARISH", "TREND_DOWN", "SELL"} or text.startswith(("SELL ", "SELL_", "SELL:")):
        return "SELL"
    return "NEUTRAL"


def _event_for_candidate(candidate: dict[str, Any], *, direction: str, e6_direction: str, e4: dict[str, Any]) -> Any:
    """Return only causally attributable event identity.

    E4's current event belongs to the direction currently supported by E6.
    A counter-direction watch must not inherit that event merely because it
    exists in the same candle.
    """
    event_id = candidate.get("event_id") or candidate.get("origin_event_id")
    if event_id:
        return event_id
    if direction == e6_direction:
        return e4.get("event_id") or e4.get("auction_event_id")
    return None


def install(pipeline_module: Any) -> None:
    if getattr(pipeline_module, "_OPPORTUNITY_LIFECYCLE_RUNTIME_BOUND", False):
        return
    original: Callable[..., Any] = pipeline_module._directional_lifecycle_current

    @wraps(original)
    def wrapped(results: dict[str, Any], decision: str, gate_passed: bool, candle: Any):
        current, leader, competition = original(results, decision, gate_passed, candle)
        e2 = results.get("E2").output if results.get("E2") else {}
        e4 = results.get("E4").output if results.get("E4") else {}
        e6 = results.get("E6").output if results.get("E6") else {}
        book = e2.get("opportunity_book") if isinstance(e2.get("opportunity_book"), dict) else {}
        e6_direction = _direction(e6.get("direction") or e6.get("direction_thesis") or e6.get("thesis_direction") or e6.get("finding"))
        candidates = book.get("candidates") if isinstance(book.get("candidates"), list) else []
        by_direction = {str(item.get("direction") or "").upper(): item for item in candidates if isinstance(item, dict)}
        for direction in ("BUY", "SELL"):
            candidate = by_direction.get(direction)
            if not candidate or str(candidate.get("state") or "").upper() in _TERMINAL:
                continue
            event_id = _event_for_candidate(candidate, direction=direction, e6_direction=e6_direction, e4=e4)
            current[direction]["event_id"] = event_id
            if event_id:
                current[direction]["origin_event_id"] = candidate.get("origin_event_id") or event_id
            else:
                current[direction].pop("origin_event_id", None)

        radar = {}
        for direction in ("BUY", "SELL"):
            item = current.get(direction) or {}
            radar[direction] = {
                "candidate": bool(item.get("candidate")),
                "state": item.get("state") or item.get("setup") or "OPPORTUNITY_WATCH",
                "thesis_proven": bool(item.get("thesis_proven")),
                "ready": bool(item.get("ready")),
                "event_id": item.get("event_id"),
                "wait_for": item.get("wait_for") or ["NEXT_CLOSED_M5_CANDLE"],
            }
        current["_radar"] = radar
        logger.info(
            "[PRODUCTION V2] OPPORTUNITY_RADAR leader=%s competition=%s BUY=%s SELL=%s e6_direction=%s execution=%s",
            leader,
            competition,
            radar["BUY"],
            radar["SELL"],
            e6_direction,
            "AUTHORIZED" if decision == "TRADE" and gate_passed else "BLOCKED",
        )
        return current, leader, competition

    pipeline_module._directional_lifecycle_current = wrapped
    pipeline_module._OPPORTUNITY_LIFECYCLE_RUNTIME_BOUND = True
