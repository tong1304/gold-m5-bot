from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .contracts import EngineResult
from .opportunity_timing import enrich_timing

RUNTIME_VERSION = "OPPORTUNITY_TIMING_MEMBRANE_V5"


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


def _observation_map(output: dict[str, Any]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    observations = output.get("observations")
    if isinstance(observations, dict):
        for key, value in observations.items():
            parsed[str(key).strip()] = value
    elif isinstance(observations, (list, tuple, set)):
        for item in observations:
            if not isinstance(item, str) or "=" not in item:
                continue
            key, value = item.split("=", 1)
            if key.strip():
                parsed[key.strip()] = value.strip()
    return parsed


def _value(output: dict[str, Any], key: str) -> Any:
    direct = output.get(key)
    if _usable(direct):
        return direct
    return _observation_map(output).get(key)


def _merge_evidence(e6: dict[str, Any], e4: dict[str, Any], e5: dict[str, Any]) -> dict[str, Any]:
    out = dict(e6)
    e4_obs = _observation_map(e4)
    e5_obs = _observation_map(e5)
    for key in ("event", "event_type", "event_level", "event_atr_frozen", "event_age_bars", "auction_state", "response_actor", "event_id", "event_candle_id"):
        value = _first_usable(e4.get(key), e4_obs.get(key), out.get(key), _observation_map(out).get(key))
        if value is not None:
            out[key] = value
    for key in ("liquidity_quality", "auction_quality"):
        value = _first_usable(e4.get(key), e4_obs.get(key), out.get(key), _observation_map(out).get(key))
        if value is not None:
            out[key] = value
    for key in ("price", "current_price", "last_price", "available_space_atr", "effective_space_atr", "space_atr"):
        value = _first_usable(e5.get(key), e5_obs.get(key), out.get(key), _observation_map(out).get(key))
        if value is not None:
            out[key] = value
    for key in ("available_space_atr_long", "available_space_atr_short"):
        value = _first_usable(e5.get(key), e5_obs.get(key), out.get(key), _observation_map(out).get(key))
        if value is not None:
            out[key] = value
    direction = str(out.get("direction") or out.get("direction_thesis") or out.get("thesis_direction") or "").upper().strip()
    if direction not in {"BUY", "SELL"}:
        finding = str(out.get("finding") or "").upper().strip()
        if finding.startswith("BUY"):
            direction = "BUY"
        elif finding.startswith("SELL"):
            direction = "SELL"
    if direction in {"BUY", "SELL"} and not _usable(out.get("available_space_atr")):
        out["available_space_atr"] = out.get("available_space_atr_long" if direction == "BUY" else "available_space_atr_short", 0.0)
    return out


def _parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _canonical_clock(out: dict[str, Any], e4: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Create one M5 clock for E6 timing from E4 event + current closed candle."""
    event_id = str(out.get("event_id") or e4.get("event_id") or e4.get("auction_event_id") or "").strip()
    event_candle = str(out.get("event_candle_id") or e4.get("event_candle_id") or "").strip()
    if not event_candle and event_id:
        event_candle = event_id.split("|", 1)[0]
    current_candle = snapshot.get("candle_close_timestamp") or snapshot.get("candle")
    event_ts = _parse_time(event_candle)
    current_ts = _parse_time(current_candle)
    if event_ts is None or current_ts is None or current_ts < event_ts:
        return {}
    age = max(0, int((current_ts - event_ts).total_seconds() // 300))
    return {"event_id": event_id, "origin_event_id": event_id, "event_candle": event_candle, "last_evaluated_candle": str(current_candle or "").strip(), "age_bars": age}


def _apply(result: EngineResult, upstream: dict[str, EngineResult], snapshot: dict[str, Any]) -> EngineResult:
    e4 = _out(upstream.get("E4")); e5 = _out(upstream.get("E5"))
    out = _merge_evidence(_out(result), e4, e5)
    anchor = _canonical_clock(out, e4, snapshot)
    if anchor:
        out["causal_event_anchor"] = anchor
        out["event_age_bars"] = anchor["age_bars"]
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
        out["candidate_type"] = "EARLY_OPPORTUNITY_CANDIDATE"
        out["confirmation_window"] = "NEXT_CLOSED_M5_CANDLE"
        out["wait_for"] = "FAST_CLOSED_CANDLE_CONFIRMATION" if timing.get("decision_speed") == "FAST" else "CLOSED_CANDLE_CONFIRMATION"
    elif timing.get("phase") == "LATE_OPPORTUNITY":
        out["wait_for"] = "NO_CHASE;WAIT_FOR_NEW_CAUSAL_EVENT"
    print("[PRODUCTION V2] OPPORTUNITY_TIMING " + f"phase={timing.get('phase')} speed={timing.get('decision_speed')} direction={timing.get('direction')} age={timing.get('event_age_bars')} quality={timing.get('evidence_quality')} space_atr={timing.get('available_space_atr')} fast={timing.get('fast_path_eligible')} chase_prohibited={timing.get('chase_prohibited')} authority=E9 source=E4_E5_CANONICAL_CLOCK membrane={RUNTIME_VERSION}", flush=True)
    return EngineResult(result.engine_id, result.name, result.gate_passed, result.score, out, result.reason_codes)


def _is_live_membrane(value: Any) -> bool:
    return callable(value) and getattr(value, "_timing_membrane_version", "") == RUNTIME_VERSION


def install(pipeline_module) -> None:
    current = getattr(pipeline_module, "_E6_RUNTIME_OVERRIDE", None) or getattr(pipeline_module, "analyze_e6")
    existing = getattr(pipeline_module, "_E6_TIMING_MEMBRANE", None)
    if _is_live_membrane(existing):
        pipeline_module._E6_RUNTIME_OVERRIDE = existing
        pipeline_module.analyze_e6 = existing
        pipeline_module._OPPORTUNITY_TIMING_HOTFIX_INSTALLED = True
        return
    if _is_live_membrane(current):
        pipeline_module._E6_TIMING_MEMBRANE = current
        pipeline_module._E6_RUNTIME_OVERRIDE = current
        pipeline_module.analyze_e6 = current
        pipeline_module._OPPORTUNITY_TIMING_HOTFIX_INSTALLED = True
        return
    original = current
    def wrapped(snapshot, upstream):
        return _apply(original(snapshot, upstream), upstream, snapshot)
    wrapped.__name__ = "timing_membrane_e6"
    wrapped.__module__ = "production_v2.opportunity_timing_runtime_hotfix"
    wrapped._timing_membrane_version = RUNTIME_VERSION
    pipeline_module.analyze_e6 = wrapped
    pipeline_module._E6_RUNTIME_OVERRIDE = wrapped
    pipeline_module._OPPORTUNITY_TIMING_HOTFIX_INSTALLED = True
    pipeline_module._E6_TIMING_MEMBRANE = wrapped
    print(f"[PRODUCTION V2] TIMING_MEMBRANE_INSTALL version={RUNTIME_VERSION} target=E6_RUNTIME_OVERRIDE", flush=True)
