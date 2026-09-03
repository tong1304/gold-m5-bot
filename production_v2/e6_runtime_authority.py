from __future__ import annotations

from typing import Any

from .contracts import EngineResult
from .e6_opportunity_guard import _direction, _fallback_opportunity, _watch


WATCH_SETUPS = {"OPPORTUNITY_WATCH", "OPPORTUNITY_CANDIDATE", "OPPORTUNITY_THESIS"}


def _out(result: Any) -> dict[str, Any]:
    return dict(getattr(result, "output", {}) or {})


def _has_no_setup(result: EngineResult) -> bool:
    out = _out(result)
    # setup_family is a strategy/family label, not proof that E6 has a setup.
    # A legacy path may populate it while setup remains empty/NO_SETUP.
    setup = str(out.get("setup") or "").upper().strip()
    finding = str(out.get("finding") or "").upper().strip()
    reasons = {
        str(code).upper().strip()
        for code in (
            *(out.get("reason_codes") or []),
            *(out.get("reasons") or []),
            *(result.reason_codes or ()),
        )
    }
    return (
        setup in {"", "NO_SETUP", "UNKNOWN", "NONE"}
        and (
            "NO_CAUSAL_OPPORTUNITY" in reasons
            or "NO CAUSAL SETUP HYPOTHESIS" in finding
            or "NO SURVIVING CAUSAL OPPORTUNITY THESIS" in finding
        )
    )


def _normalize_watch_semantics(output: dict[str, Any]) -> dict[str, Any]:
    """Keep human-readable E6 finding aligned with structured watch state."""
    normalized = dict(output)
    setup = str(normalized.get("setup") or "").upper().strip()
    if setup not in WATCH_SETUPS:
        return normalized
    if normalized.get("watch_only") is not True or normalized.get("trade_ready") is True:
        return normalized

    direction = _direction(
        normalized.get("direction"),
        normalized.get("bias"),
        normalized.get("market_direction"),
        normalized.get("thesis_direction"),
        normalized.get("direction_thesis"),
    )
    if direction not in {"BUY", "SELL"}:
        direction = "NEUTRAL"
    stage = str(
        normalized.get("stage")
        or normalized.get("opportunity_stage")
        or normalized.get("thesis_status")
        or "FORMING"
    ).strip().upper()
    stage_text = {
        "FORMING": "forming",
        "CONTESTED": "contested",
        "VALIDATING": "being validated",
        "WATCHING": "being watched",
    }.get(stage, stage.lower().replace("_", " "))
    normalized["finding"] = (
        f"{direction} opportunity is {stage_text}; causal setup is not yet proven."
        if direction != "NEUTRAL"
        else f"Opportunity is {stage_text}; causal setup is not yet proven."
    )
    normalized.setdefault("next_required_event", "NEXT_CLOSED_M5_CANDLE")
    return normalized


def install(e6_module) -> None:
    if getattr(e6_module, "_E6_RUNTIME_AUTHORITY_INSTALLED", False):
        return

    original = e6_module.analyze_e6

    def runtime_authority(market_data, upstream):
        result = original(market_data, upstream)
        if not isinstance(result, EngineResult):
            return result

        out = _out(result)
        setup = str(out.get("setup") or "").upper().strip()
        if setup in WATCH_SETUPS and out.get("watch_only") is True and out.get("trade_ready") is not True:
            normalized = _normalize_watch_semantics(out)
            if normalized != out:
                return EngineResult(
                    result.engine_id,
                    result.name,
                    result.gate_passed,
                    result.score,
                    normalized,
                    result.reason_codes,
                )
            return result

        if not _has_no_setup(result):
            return result

        candidate = _fallback_opportunity(upstream)
        if candidate is None:
            return result

        watch = _watch(result, candidate)
        watch_out = _normalize_watch_semantics(dict(watch.output or {}))
        watch_out["runtime_authority"] = "E6_FINAL_OPPORTUNITY_MEMBRANE"
        watch_out["runtime_rescue_reason"] = "CAUSAL_E1_E5_EVIDENCE_SURVIVES_LEGACY_NO_SETUP"
        watch_out["runtime_direction_source"] = _direction(
            candidate.get("direction"),
        )
        return EngineResult(
            watch.engine_id,
            watch.name,
            False,
            watch.score,
            watch_out,
            watch.reason_codes,
        )

    e6_module.analyze_e6 = runtime_authority
    e6_module._E6_RUNTIME_AUTHORITY_INSTALLED = True
