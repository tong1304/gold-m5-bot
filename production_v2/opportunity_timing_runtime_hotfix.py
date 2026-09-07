from __future__ import annotations

from typing import Any

from .contracts import EngineResult
from .opportunity_timing import enrich_timing

RUNTIME_VERSION = "OPPORTUNITY_TIMING_MEMBRANE_V2"


def _out(result: Any) -> dict[str, Any]:
    return dict(getattr(result, "output", {}) or {})


def _usable(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    try:
        return float(value) != 0.0
    except (TypeError, ValueError):
        return True


def _first_usable(*values: Any) -> Any:
    for value in values:
        if _usable(value):
            return value
    return None


def _merge_evidence(e6: dict[str, Any], e4: dict[str, Any], e5: dict[str, Any]) -> dict[str, Any]:
    """Build timing evidence with upstream E4/E5 taking precedence over stale zeroes."""
    out = dict(e6)
    for key in ("event", "event_type", "event_level", "event_atr_frozen", "event_age_bars", "auction_state", "response_actor"):
        value = _first_usable(e4.get(key), out.get(key))
        if value is not None:
            out[key] = value
    for key in ("liquidity_quality", "auction_quality"):
        value = _first_usable(e4.get(key), out.get(key))
        if value is not None:
            out[key] = value
    for key in ("price", "current_price", "last_price"):
        value = _first_usable(e5.get(key), out.get(key))
        if value is not None:
            out[key] = value
    for key in ("available_space_atr_long", "available_space_atr_short"):
        value = _first_usable(e5.get(key), out.get(key))
        if value is not None:
            out[key] = value
    direction = str(out.get("direction") or out.get("direction_thesis") or out.get("thesis_direction") or "").upper().strip()
    if direction in {"BUY", "SELL"} and not _usable(out.get("available_space_atr")):
        out["available_space_atr"] = out.get("available_space_atr_long" if direction == "BUY" else "available_space_atr_short", 0.0)
    return out


def _apply(result: EngineResult, upstream: dict[str, EngineResult]) -> EngineResult:
    e4 = _out(upstream.get("E4")); e5 = _out(upstream.get("E5"))
    out = _merge_evidence(_out(result), e4, e5)
    timing = enrich_timing(out).get("opportunity_timing") or {}
    out["opportunity_timing"] = timing
    out["opportunity_phase_speed"] = timing.get("phase")
    out["opportunity_decision_speed"] = timing.get("decision_speed")
    out["opportunity_fast_path"] = bool(timing.get("fast_path_eligible"))
    out["opportunity_chase_prohibited"] = bool(timing.get("chase_prohibited"))
    out["opportunity_lifecycle_state"] = {"EARLY_OPPORTUNITY":"EARLY","CONFIRMED_OPPORTUNITY":"CONFIRMED","LATE_OPPORTUNITY":"DECAYING","NO_DIRECTIONAL_OPPORTUNITY":"NO_OPPORTUNITY"}.get(timing.get("phase"), "FORMING")
    out["execution_authority"] = "E9"
    out["timing_membrane_version"] = RUNTIME_VERSION
    if timing.get("phase") == "EARLY_OPPORTUNITY":
        # EARLY is always eligible for E7 evaluation. FAST/SLOW only changes cadence.
        out["candidate_type"] = "EARLY_OPPORTUNITY_CANDIDATE"
        out["confirmation_window"] = "NEXT_CLOSED_M5_CANDLE"
        out["wait_for"] = "FAST_CLOSED_CANDLE_CONFIRMATION" if timing.get("decision_speed") == "FAST" else "CLOSED_CANDLE_CONFIRMATION"
    elif timing.get("phase") == "LATE_OPPORTUNITY":
        out["wait_for"] = "NO_CHASE;WAIT_FOR_NEW_CAUSAL_EVENT"
    print("[PRODUCTION V2] OPPORTUNITY_TIMING " + f"phase={timing.get('phase')} speed={timing.get('decision_speed')} direction={timing.get('direction')} age={timing.get('event_age_bars')} quality={timing.get('evidence_quality')} space_atr={timing.get('available_space_atr')} fast={timing.get('fast_path_eligible')} chase_prohibited={timing.get('chase_prohibited')} authority=E9 source=E4_E5_RUNTIME_MERGE membrane={RUNTIME_VERSION}", flush=True)
    return EngineResult(result.engine_id, result.name, result.gate_passed, result.score, out, result.reason_codes)


def install(pipeline_module) -> None:
    if getattr(pipeline_module, "_OPPORTUNITY_TIMING_HOTFIX_INSTALLED", False):
        return
    original = getattr(pipeline_module, "_E6_RUNTIME_OVERRIDE", None) or pipeline_module.analyze_e6
    def wrapped(snapshot, upstream):
        return _apply(original(snapshot, upstream), upstream)
    wrapped.__name__ = "timing_membrane_e6"
    wrapped.__module__ = "production_v2.opportunity_timing_runtime_hotfix"
    wrapped._timing_membrane_version = RUNTIME_VERSION
    pipeline_module.analyze_e6 = wrapped
    pipeline_module._E6_RUNTIME_OVERRIDE = wrapped
    pipeline_module._OPPORTUNITY_TIMING_HOTFIX_INSTALLED = True
    pipeline_module._E6_TIMING_MEMBRANE = wrapped
    print(f"[PRODUCTION V2] TIMING_MEMBRANE_INSTALL version={RUNTIME_VERSION} target=E6_RUNTIME_OVERRIDE", flush=True)
