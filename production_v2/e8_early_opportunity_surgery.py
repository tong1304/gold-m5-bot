from __future__ import annotations

from typing import Any

from .contracts import EngineResult

_EARLY_CANDIDATES = {"EARLY_OPPORTUNITY_CANDIDATE", "OPPORTUNITY_CANDIDATE"}
_WATCH_SETUPS = {"OPPORTUNITY_WATCH", "OPPORTUNITY_CANDIDATE", "OPPORTUNITY_THESIS"}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _out(result: Any) -> dict[str, Any]:
    return dict(getattr(result, "output", {}) or {})


def install(pipeline_module: Any) -> None:
    if getattr(pipeline_module, "_E8_EARLY_OPPORTUNITY_SURGERY_INSTALLED", False):
        return
    original = pipeline_module.analyze_e8

    def wrapped(snapshot: dict[str, Any], results: dict[str, EngineResult]):
        current = original(snapshot, results)
        current_out = _out(current)
        if _text(current_out.get("finding")) != "NOT_APPLICABLE":
            return current

        e6_result = results.get("E6")
        e6 = _out(e6_result) if e6_result else {}
        candidate_type = _text(e6.get("candidate_type"))
        direction = _text(e6.get("direction") or e6.get("direction_thesis") or e6.get("thesis_direction"))
        if direction not in {"BUY", "SELL"}:
            return current
        if candidate_type not in _EARLY_CANDIDATES and not bool(e6.get("early_candidate")):
            return current

        # E8 may screen economics before E7 confirmation, but it must never
        # inherit a WATCH setup that the applicability guard treats as absent.
        # This provisional label is explicitly non-tradeable and exists only
        # to answer: "if confirmation arrives, is the geometry/economics viable?"
        provisional = dict(e6)
        setup = _text(provisional.get("setup") or provisional.get("setup_family"))
        if setup in _WATCH_SETUPS or not setup:
            provisional["setup"] = "EARLY_OPPORTUNITY"
        provisional["watch_only"] = False
        provisional["economic_screen_only"] = True
        provisional["trade_ready"] = False
        provisional["thesis_status"] = _text(provisional.get("thesis_status")) or "FORMING"

        shadow = dict(results)
        shadow["E6"] = EngineResult(
            e6_result.engine_id, e6_result.name, e6_result.gate_passed,
            e6_result.score, provisional, e6_result.reason_codes,
        )
        screened = original(snapshot, shadow)
        out = dict(screened.output or {})
        out["economic_stage"] = "EARLY_OPPORTUNITY_SCREEN"
        out["economic_screen_only"] = True
        out["trade_authorized"] = False
        out["confirmation_required_before_trade"] = True
        out["source_e6_candidate_type"] = candidate_type
        out["original_e6_setup"] = setup or "OPPORTUNITY_WATCH"
        reasons = list(out.get("reason_codes") or out.get("reasons") or [])
        if "EARLY_OPPORTUNITY_ECONOMICS_SCREEN" not in reasons:
            reasons.append("EARLY_OPPORTUNITY_ECONOMICS_SCREEN")
        out["reason_codes"] = reasons
        out["reasons"] = reasons
        return EngineResult("E8", screened.name, False, screened.score, out, tuple(dict.fromkeys(reasons)))

    pipeline_module.analyze_e8 = wrapped
    pipeline_module._E8_EARLY_OPPORTUNITY_SURGERY_INSTALLED = True
    print("[PRODUCTION V2] E8_EARLY_OPPORTUNITY_SURGERY binding=EARLY_ECONOMICS_SCREEN_ONLY", flush=True)
