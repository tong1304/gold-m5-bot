from __future__ import annotations

import logging
from functools import wraps
from typing import Any

from . import opportunity_lifecycle_progression as progression

logger = logging.getLogger(__name__)
_TERMINAL = {"INVALIDATED", "EXPIRED", "REPLACED", "EXECUTED"}
_VALID = {"BUY", "SELL"}


def _direction(value: Any) -> str:
    text = str(value or "").upper().strip()
    if text in {"BUY", "BULLISH", "UP", "TREND_UP"} or text.startswith(("BUY ", "BUY_", "BUY:")):
        return "BUY"
    if text in {"SELL", "BEARISH", "DOWN", "TREND_DOWN"} or text.startswith(("SELL ", "SELL_", "SELL:")):
        return "SELL"
    return "NEUTRAL"


def _e6_direction(e6: dict[str, Any]) -> str:
    return _direction(e6.get("direction") or e6.get("direction_thesis") or e6.get("thesis_direction") or e6.get("opportunity_direction") or e6.get("finding"))


def _is_early_watch(e6: dict[str, Any]) -> bool:
    candidate = str(e6.get("candidate_type") or "").upper().strip()
    phase = str(e6.get("opportunity_phase_speed") or "").upper().strip()
    return candidate == "EARLY_OPPORTUNITY_CANDIDATE" or phase == "EARLY_OPPORTUNITY"


def _canonical_event(e4: dict[str, Any], causal_anchor: Any) -> Any:
    if isinstance(causal_anchor, dict) and causal_anchor.get("event_id"):
        return causal_anchor["event_id"]
    return e4.get("event_id") or e4.get("auction_event_id") or e4.get("liquidity_event_id")


def install(pipeline_module: Any) -> None:
    if getattr(pipeline_module, "_P0_OPPORTUNITY_INTEGRITY_BOUND", False):
        return

    original_directional = pipeline_module._directional_lifecycle_current
    original_lifecycle = pipeline_module.advance_opportunity_directions

    @wraps(original_directional)
    def canonical_directional(results: dict[str, Any], decision: str, gate_passed: bool, candle: Any, *args: Any, **kwargs: Any):
        current, leader, competition = original_directional(results, decision, gate_passed, candle, *args, **kwargs)
        e6 = results.get("E6").output if results.get("E6") and isinstance(results.get("E6").output, dict) else {}
        e4 = results.get("E4").output if results.get("E4") and isinstance(results.get("E4").output, dict) else {}
        d6 = _e6_direction(e6)
        event_id = _canonical_event(e4, kwargs.get("causal_anchor") or (args[0] if args else None))
        if d6 in _VALID:
            item = dict(current.get(d6) or {})
            item["candidate"] = True
            item["direction"] = d6
            item["event_id"] = event_id or item.get("event_id")
            item["origin_event_id"] = item.get("origin_event_id") or item.get("event_id")
            if _is_early_watch(e6):
                item["setup"] = "OPPORTUNITY_WATCH"
                item["thesis_proven"] = bool(item.get("thesis_proven", False))
                item["ready"] = False if not (decision == "TRADE" and gate_passed) else item.get("ready", False)
                item["candidate_type"] = "EARLY_OPPORTUNITY_CANDIDATE"
                item["wait_for"] = e6.get("wait_for") or ("FAST_CLOSED_CANDLE_CONFIRMATION" if str(e6.get("opportunity_decision_speed") or "").upper() == "FAST" else "CLOSED_CANDLE_CONFIRMATION")
                item["opportunity_phase_speed"] = "EARLY_OPPORTUNITY"
            current[d6] = item
            # A stale counter-direction event is not allowed to become the E6 event.
            other = "SELL" if d6 == "BUY" else "BUY"
            if other in current and current[other].get("event_id") and not current[other].get("candidate"):
                current[other] = dict(current[other]); current[other].pop("event_id", None); current[other].pop("origin_event_id", None)
            leader = d6 if bool(item.get("candidate")) else leader
        return current, leader, competition

    @wraps(original_lifecycle)
    def canonical_lifecycle(previous: dict[str, Any] | None, current_by_direction: dict[str, dict[str, Any]], *, leader: str = "NEUTRAL", competition: str = "UNCONTESTED"):
        result = original_lifecycle(previous, current_by_direction, leader=leader, competition=competition)
        previous_map = previous.get("opportunities") if isinstance(previous, dict) and isinstance(previous.get("opportunities"), dict) else {}
        opportunities = dict(result.get("opportunities") or {})
        for direction in ("BUY", "SELL"):
            item = dict(opportunities.get(direction) or {})
            current = dict(current_by_direction.get(direction) or {})
            if not current.get("candidate"):
                continue
            # The opportunity lifecycle is the production path. Apply the same
            # stage machine here, so promotion cannot live only in a parallel module.
            prior = previous_map.get(direction) if isinstance(previous_map.get(direction), dict) else {}
            stage_input = {**current, "opportunity_id": item.get("opportunity_id"), "event_id": item.get("event_id")}
            staged = progression.advance_lifecycle_stage(prior, stage_input)
            for key in ("lifecycle_stage", "wait_for_stage", "stage_history", "stage_candle", "terminal_stage", "terminal_reason"):
                if key in staged:
                    item[key] = staged[key]
            if item.get("opportunity_id") and staged.get("opportunity_id") and item.get("opportunity_id") != staged.get("opportunity_id"):
                item["previous_opportunity_id"] = item.get("opportunity_id")
                item["opportunity_id"] = staged["opportunity_id"]
            item["canonical_direction"] = direction
            item["canonical_event_id"] = item.get("event_id") or current.get("event_id")
            item["identity_source"] = "E6_CAUSAL_EVENT_CANONICAL"
            opportunities[direction] = item
        result["opportunities"] = opportunities
        active = [d for d in ("BUY", "SELL") if str(opportunities.get(d, {}).get("state") or "").upper() in {"WATCHING", "WAITING", "READY"}]
        result["active_directions"] = active
        if leader not in _VALID or leader not in active:
            leader = active[0] if active else "NEUTRAL"
        result["leader"] = leader
        result["direction"] = leader
        result["opportunity_id"] = opportunities.get(leader, {}).get("opportunity_id") if leader in opportunities else None
        result["state"] = opportunities.get(leader, {}).get("state", "IDLE") if leader in opportunities else "IDLE"
        result["bars_waited"] = opportunities.get(leader, {}).get("bars_waited", 0) if leader in opportunities else 0
        result["p0_integrity"] = {"canonical_identity": True, "single_production_lifecycle_path": True, "e6_lifecycle_synchronized": True}
        logger.info("[PRODUCTION V2] P0_INTEGRITY leader=%s active=%s BUY_ID=%s SELL_ID=%s", leader, active, opportunities.get("BUY", {}).get("opportunity_id"), opportunities.get("SELL", {}).get("opportunity_id"))
        return result

    pipeline_module._directional_lifecycle_current = canonical_directional
    pipeline_module.advance_opportunity_directions = canonical_lifecycle
    pipeline_module._P0_OPPORTUNITY_INTEGRITY_BOUND = True
