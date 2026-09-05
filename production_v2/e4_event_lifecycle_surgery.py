from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .contracts import EngineResult

VERSION = "E4_EVENT_LIFECYCLE_SURGERY_V5"
CONFIRM_BARS = 2
FOLLOW_WINDOW = 5
INTERACTION_ATR = 0.05
MIN_DISPLACEMENT_ATR = 0.20
PENDING_STATES = {"PENDING", "DEVELOPING", "FORMING", "AWAITING_CONFIRMATION", "CONFIRMATION_PENDING"}
TERMINAL = {"CONFIRMED", "INVALIDATED", "EXPIRED"}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _out(result: Any) -> dict[str, Any]:
    value = getattr(result, "output", {})
    return dict(value) if isinstance(value, dict) else {}


def _num(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value == value else None


def _timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _bar_timestamp(bar: dict[str, Any]) -> datetime | None:
    for key in ("timestamp", "time", "datetime", "date", "open_time", "close_time"):
        parsed = _timestamp(bar.get(key))
        if parsed is not None:
            return parsed
    return None


def _event_id(output: dict[str, Any]) -> str:
    event = output.get("event") if isinstance(output.get("event"), dict) else {}
    return str(output.get("event_candle_id") or event.get("event_candle_id") or str(output.get("event_id") or event.get("event_id") or "").split("|", 1)[0] or "")


def _event_index(output: dict[str, Any], bars: list[dict[str, Any]]) -> int:
    event = output.get("event") if isinstance(output.get("event"), dict) else {}
    wanted = _event_id(output)
    wanted_ts = _timestamp(wanted)
    for i, bar in enumerate(bars):
        bar_ts = _bar_timestamp(bar)
        if wanted and any(str(bar.get(k)) == wanted for k in ("timestamp", "time", "datetime", "date", "open_time", "close_time")):
            return i
        if wanted_ts is not None and bar_ts is not None and wanted_ts == bar_ts:
            return i
    for key in ("event_index", "bar_index", "index"):
        value = output.get(key) if key != "index" else event.get("index")
        try:
            idx = int(value)
            if 0 <= idx < len(bars):
                return idx
        except (TypeError, ValueError):
            pass
    return -1


def _direction(output: dict[str, Any]) -> str:
    event = output.get("event") if isinstance(output.get("event"), dict) else {}
    values = [event.get("directional_implication"), output.get("directional_implication"), output.get("direction"), event.get("direction")]
    event_id = str(output.get("event_id") or event.get("event_id") or "")
    if event_id:
        values.append(event_id.rsplit("|", 1)[-1])
    for value in values:
        text = _text(value)
        if text in {"UP", "BUY", "BULLISH"} or text.startswith(("BUY_", "BUY:", "UP_", "UP:")):
            return "UP"
        if text in {"DOWN", "SELL", "BEARISH"} or text.startswith(("SELL_", "SELL:", "DOWN_", "DOWN:")):
            return "DOWN"
    return "NEUTRAL"


def _level(output: dict[str, Any]) -> float | None:
    event = output.get("event") if isinstance(output.get("event"), dict) else {}
    value = _num(output.get("event_level"))
    return value if value is not None else _num(event.get("event_level"))


def _atr(output: dict[str, Any]) -> float:
    event = output.get("event") if isinstance(output.get("event"), dict) else {}
    return _num(event.get("event_atr") or output.get("event_atr") or output.get("event_atr_frozen") or output.get("atr14_current")) or 0.0


def _repair(output: dict[str, Any], bars: list[dict[str, Any]], current_candle: Any) -> dict[str, Any]:
    state = _text(output.get("auction_state") or output.get("auction_phase") or output.get("state"))
    if state not in PENDING_STATES or not bars:
        return output
    idx = _event_index(output, bars)
    if idx < 0:
        return output

    event_ts = _timestamp(_event_id(output))
    current_ts = _timestamp(current_candle) or _bar_timestamp(bars[-1])
    age_by_index = max(0, len(bars) - 1 - idx)
    age_by_time = 0
    if event_ts is not None and current_ts is not None and current_ts >= event_ts:
        age_by_time = int((current_ts - event_ts).total_seconds() // 300)
    age = max(age_by_index, age_by_time)

    direction = _direction(output)
    level = _level(output)
    atr = _atr(output)
    if direction == "NEUTRAL" or level is None or atr <= 0:
        repaired = dict(output)
        repaired.update(event_age_bars=age, event_index=idx, auction_lifecycle_repaired=True, auction_lifecycle_repair_version=VERSION, auction_lifecycle_repair_reason="AGE_ONLY_NO_DIRECTIONAL_PROOF")
        reasons = [str(x) for x in list(repaired.get("reason_codes") or repaired.get("reasons") or []) if str(x)]
        if "E4_EVENT_AGE_REPAIRED" not in reasons: reasons.append("E4_EVENT_AGE_REPAIRED")
        repaired["reason_codes"] = reasons; repaired["reasons"] = reasons
        return repaired

    post = bars[idx + 1:]
    checks: list[dict[str, Any]] = []
    consecutive = 0
    lifecycle = "PENDING"
    terminal_reason = "FOLLOW_THROUGH_ABSENT"
    for bar in post:
        close = _num(bar.get("close"))
        if close is None: continue
        if direction == "UP":
            hold = close > level + atr * INTERACTION_ATR; opposite = close < level - atr * INTERACTION_ATR; displacement = (close - level) / atr
        else:
            hold = close < level - atr * INTERACTION_ATR; opposite = close > level + atr * INTERACTION_ATR; displacement = (level - close) / atr
        meaningful = bool(hold and displacement >= MIN_DISPLACEMENT_ATR)
        if opposite:
            lifecycle = "INVALIDATED"; terminal_reason = "POST_EVENT_RECLAMATION"; consecutive = 0
        elif meaningful:
            consecutive += 1
            if consecutive >= CONFIRM_BARS: lifecycle = "CONFIRMED"; terminal_reason = "FOLLOW_THROUGH_CONFIRMED"
        else:
            consecutive = 0
        checks.append({"candle_id": str(bar.get("timestamp") or bar.get("time") or ""), "close": close, "hold": hold, "displacement_atr": round(displacement, 6), "meaningful": meaningful, "consecutive": consecutive})
        if lifecycle in TERMINAL: break

    if lifecycle == "PENDING" and age >= FOLLOW_WINDOW:
        lifecycle = "EXPIRED"; terminal_reason = "EVENT_EXPIRED"

    repaired = dict(output)
    repaired.update(auction_state=lifecycle, auction_phase=lifecycle, event_age_bars=age, event_index=idx, follow_through_bars=consecutive, required_confirmation_bars=CONFIRM_BARS, confirmation_horizon=FOLLOW_WINDOW, follow_through_checks=checks, auction_lifecycle_repaired=True, auction_lifecycle_repair_version=VERSION, auction_lifecycle_repair_reason=terminal_reason)
    reasons = [str(x) for x in list(repaired.get("reason_codes") or repaired.get("reasons") or []) if str(x)]
    code = "E4_EVENT_AGE_REPAIRED" if lifecycle == "PENDING" else f"E4_AUCTION_{lifecycle}"
    if code not in reasons: reasons.append(code)
    repaired["reason_codes"] = reasons; repaired["reasons"] = reasons
    if lifecycle == "CONFIRMED": repaired["directional_implication"] = direction; repaired["auction_confirmation"] = "FOLLOW_THROUGH_CONFIRMED"
    elif lifecycle == "INVALIDATED": repaired["directional_implication"] = "NEUTRAL"; repaired["auction_confirmation"] = "POST_EVENT_RECLAMATION"
    return repaired


def _repair_result(result: EngineResult, snapshot: dict[str, Any]) -> EngineResult:
    bars = [b for b in (snapshot.get("bars") or []) if isinstance(b, dict)] if isinstance(snapshot, dict) else []
    current = None
    if isinstance(snapshot, dict):
        for key in ("evaluation_candle_timestamp", "current_candle_timestamp", "candle_timestamp", "current_candle", "candle_close_timestamp", "data_cutoff_timestamp"):
            if snapshot.get(key): current = snapshot.get(key); break
    before = _out(result)
    after = _repair(before, bars, current)
    if after == before:
        print(f"[PRODUCTION V2] E4_EVENT_LIFECYCLE_SURGERY version={VERSION} action=SKIP state={before.get('auction_state')} event_candle={_event_id(before)} bars={len(bars)} current={current}", flush=True)
        return result
    print(f"[PRODUCTION V2] E4_EVENT_LIFECYCLE_SURGERY version={VERSION} action=REPAIR state={after.get('auction_state')} age={after.get('event_age_bars')} event_candle={_event_id(after)} current={current} reason={after.get('auction_lifecycle_repair_reason')}", flush=True)
    return EngineResult(result.engine_id, result.name, result.gate_passed, result.score, after, tuple(after.get("reason_codes", result.reason_codes)))


def install(pipeline_module: Any) -> None:
    if getattr(pipeline_module, "_E4_EVENT_LIFECYCLE_SURGERY_INSTALLED", False): return
    original_analyze = pipeline_module.analyze_e4

    def patched_analyze_e4(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
        return _repair_result(original_analyze(snapshot, upstream), snapshot)

    pipeline_module.analyze_e4 = patched_analyze_e4
    pipeline_module._E4_EVENT_LIFECYCLE_SURGERY_INSTALLED = True

    print(f"[PRODUCTION V2] E4_BINDING version={VERSION} module={pipeline_module.__name__} analyze={pipeline_module.analyze_e4.__module__}.{pipeline_module.analyze_e4.__name__}", flush=True)

    try:
        from .e5_e6_directional_evidence_surgery import install as install_e5_e6
        install_e5_e6(pipeline_module)
    except Exception as exc:
        print(f"[PRODUCTION V2] E5_E6_DIRECTIONAL_EVIDENCE_SURGERY install_error={exc}", flush=True)
