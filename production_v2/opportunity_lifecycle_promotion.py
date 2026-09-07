from __future__ import annotations

from typing import Any

from . import opportunity_lifecycle_progression as progression

STAGES = tuple(progression.STAGES)
STAGE_RANK = dict(progression.STAGE_RANK)
TERMINAL_STAGES = set(progression.TERMINAL_STAGES)


def _safe_stage_input(current: dict[str, Any]) -> dict[str, Any]:
    """Keep downstream gates causally dependent on their upstream proof."""
    stage = dict(current or {})
    thesis = bool(stage.get("thesis_proven"))
    e7 = bool(stage.get("e7_confirmed")) or str(stage.get("e7_confirmation_state") or stage.get("confirmation_state") or "").upper() in {"PASS", "PASSED", "CONFIRMED", "TRIGGER_CONFIRMED", "PROVEN", "VALIDATED", "TRADE_READY"}
    e8 = bool(stage.get("e8_ready"))
    if not thesis:
        stage.pop("e7_confirmed", None); stage.pop("e7_confirmation_state", None); stage.pop("confirmation_state", None); e7 = False
    if not e7:
        stage.pop("e8_ready", None); e8 = False
    if not e8:
        stage.pop("e9_trade", None)
    return stage


def install() -> None:
    """Remove only artificial one-stage delay while preserving causal gate order."""
    if getattr(progression, "_LIFECYCLE_PROMOTION_INSTALLED", False):
        return

    original = progression.advance_lifecycle_stage

    def promoted(previous: dict[str, Any] | None, current: dict[str, Any] | None) -> dict[str, Any]:
        previous_dict = dict(previous or {})
        current_dict = _safe_stage_input(dict(current or {}))
        result = original(previous_dict, current_dict)
        requested = progression._requested_stage(current_dict)
        previous_stage = str(previous_dict.get("lifecycle_stage") or "IDLE").upper().strip()
        result_stage = str(result.get("lifecycle_stage") or "IDLE").upper().strip()
        if requested in TERMINAL_STAGES or requested not in STAGE_RANK:
            return result
        if result_stage not in STAGE_RANK or STAGE_RANK[requested] <= STAGE_RANK[result_stage]:
            return result

        synthetic_previous = dict(previous_dict)
        synthetic_previous["lifecycle_stage"] = STAGES[STAGE_RANK[requested] - 1] if STAGE_RANK[requested] else "IDLE"
        promoted_result = original(synthetic_previous, current_dict)
        if promoted_result.get("lifecycle_stage") != requested:
            return result

        history = list(previous_dict.get("stage_history") or result.get("stage_history") or [])
        seen = {str(item.get("stage") or "").upper().strip() for item in history if isinstance(item, dict)}
        start_rank = STAGE_RANK.get(previous_stage, -1)
        for index in range(max(0, start_rank + 1), STAGE_RANK[requested] + 1):
            stage = STAGES[index]
            if stage not in seen:
                history.append({"stage": stage, "candle": str(current_dict.get("candle") or "")})
                seen.add(stage)
        promoted_result["stage_history"] = history
        promoted_result["stage_candle"] = str(current_dict.get("candle") or promoted_result.get("stage_candle") or "")
        return promoted_result

    progression.advance_lifecycle_stage = promoted
    progression._LIFECYCLE_PROMOTION_INSTALLED = True
    try:
        from . import opportunity_lifecycle_progression_surgery as surgery
        surgery.advance_lifecycle_stage = promoted
    except Exception:
        pass
