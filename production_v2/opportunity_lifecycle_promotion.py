from __future__ import annotations

from typing import Any

from . import opportunity_lifecycle_progression as progression

STAGES = tuple(progression.STAGES)
STAGE_RANK = dict(progression.STAGE_RANK)
TERMINAL_STAGES = set(progression.TERMINAL_STAGES)


def install() -> None:
    """Allow one closed-candle evaluation to promote to the highest proven stage.

    The legacy progression helper intentionally advances one rank at a time.
    That creates an artificial delay when E4/E6/E7/E8/E9 prove several gates on
    the same closed candle. This membrane preserves all existing gate checks,
    identity rules, terminal handling, and E9 authority, but removes only that
    artificial one-stage-per-candle bottleneck.
    """
    if getattr(progression, "_LIFECYCLE_PROMOTION_INSTALLED", False):
        return

    original = progression.advance_lifecycle_stage

    def promoted(previous: dict[str, Any] | None, current: dict[str, Any] | None) -> dict[str, Any]:
        previous_dict = dict(previous or {})
        current_dict = dict(current or {})
        result = original(previous_dict, current_dict)

        requested = progression._requested_stage(current_dict)
        previous_stage = str(previous_dict.get("lifecycle_stage") or "IDLE").upper().strip()
        result_stage = str(result.get("lifecycle_stage") or "IDLE").upper().strip()

        if requested in TERMINAL_STAGES or requested not in STAGE_RANK:
            return result
        if result_stage not in STAGE_RANK or STAGE_RANK[requested] <= STAGE_RANK[result_stage]:
            return result

        # Re-run the legacy state machine with a synthetic immediate predecessor
        # so every existing stage-specific safety rule remains authoritative.
        synthetic_previous = dict(previous_dict)
        synthetic_previous["lifecycle_stage"] = STAGES[STAGE_RANK[requested] - 1] if STAGE_RANK[requested] else "IDLE"
        promoted_result = original(synthetic_previous, current_dict)
        if promoted_result.get("lifecycle_stage") != requested:
            return result

        # Preserve the real prior history and explicitly record any crossed
        # lifecycle stages so promotion is auditable rather than a hidden jump.
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

    # The lifecycle enrichment module imported the helper by name, so update
    # its local reference as well. This keeps the production boundary coherent.
    try:
        from . import opportunity_lifecycle_progression_surgery as surgery
        surgery.advance_lifecycle_stage = promoted
    except Exception:
        # The canonical progression module is still patched; package bootstrap
        # may import the surgery module later and refresh its local reference.
        pass
