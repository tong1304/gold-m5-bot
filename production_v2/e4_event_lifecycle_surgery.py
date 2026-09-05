from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .contracts import EngineResult

VERSION = "E4_EVENT_LIFECYCLE_SURGERY_V2"
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


def _bar_id(bar: dict[str, Any]) -> str | None:
    for key in ("timestamp", "time", "datetime", "date", "candle", "open_time", "close_time"):
        value = bar.get(key)
        if value not in (None, ""):
            return str(value)
    return None


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


def _event_candle_id(output: dict[str, Any], event: dict[str, Any]) -> str:
    direct = output.get("event_candle_id") or event.get("event_candle_id")
    if direct not in (None, ""):
        return str(direct)
    event_id = str(output.get("event_id") or event.get("event_id") or "")
    if event_id:
        return event_id.split("|", 1)[0]
    return ""


def _event_index(output: dict[str, Any], bars: list[dict[str, Any]]) -> int:
    event = output.get("event") if isinstance(output.get("event"), dict) else {}
    candle_id = _event_candle_id(output, event)
    if candle_id:
        target_ts = _timestamp(candle_id)
        for i, bar in enumerate(bars):
            bar_id = _bar_id(bar)
            if bar_id == candle_id:
                return i
            if target_ts is not None:
                bar_ts = _timestamp(bar_id)
                if bar_ts is not None and bar_ts == target_ts:
                    return i
    for key in ("index", "event_index", "bar_index"):
        value = event.get(key) if key == "index" else output.get(key)
        try:
            idx = int(value)
            if 0 <= idx < len(bars):
                return idx
        except (TypeError, ValueError):
            pass
    return -1


def _direction(output: dict[str, Any], event: dict[str, Any]) -> str:
    candidates = [
        event.get("directional_implication"),
        output.get("directional_implication"),
        output.get("direction"),
        event.get("direction"),
    ]
    event_id = str(output.get("event_id") or event.get("event_id") or "")
    if event_id:
        candidates.append(event_id.rsplit("|", 1)[-1])
    for value in candidates:
        text = _text(value)
        if text in {"UP", "BUY", "BULLISH"} or text.startswith(("BUY_", "BUY:", "UP_", "UP:")):
            return "UP"
        if text in {"DOWN", "SELL", "BEARISH"} or text.startswith(("SELL_", "SELL:", "DOWN_", "DOWN:")):
            return "DOWN"
    return "NEUTRAL"


def _level(output: dict[str, Any], event: dict[str, Any]) -> float | None:
    direct = _num(output.get("event_level"))
    return direct if direct is not None else _num(event.get("event_level"))


def _event_atr(output: dict[str, Any], event: dict[str, Any]) -> float:
    return _num(event.get("event_atr") or output.get("event_atr") or output.get("event_atr_frozen") or output.get("atr14_current")) or 0.0


def _repair(output: dict[str, Any], bars: list[dict[str, Any]], current_candle: Any = None) -> dict[str, Any]:
    event = output.get("event") if isinstance(output.get("event"), dict) else {}
    state = _text(output.get("auction_state") or output.get("auction_phase") or output.get("state"))
    if state not in PENDING_STATES:
        return output
    idx = _event_index(output, bars)
    if idx < 0:
        return output

    # The original E4 output is recalculated on every candle and can keep age=0.
    # Age must therefore be derived from the immutable event candle versus the
    # current closed candle, with the bar sequence as the authoritative fallback.
    current_idx = len(bars) - 1
    event_ts = _timestamp(_event_candle_id(output, event))
    current_ts = _timestamp(current_candle) or _timestamp(_bar_id(bars[-1])) if bars else None
    age = max(0, current_idx - idx)
    if event_ts is not None and current_ts is not None:
        delta_seconds = (current_ts - event_ts).total_seconds()
        if delta_seconds >= 0:
            timestamp_age = int(delta_seconds // 300)
            if timestamp_age >= 0:
                age = max(age, timestamp_age)

    direction = _direction(output, event)
    level = _level(output, event)
    event_atr = _event_atr(output, event)
    if direction == "NEUTRAL" or level is None or event_atr <= 0:
        return output

    post = bars[idx + 1:]
    if not post and age <= 0:
        return output

    checks: list[dict[str, Any]] = []
    consecutive = 0
    lifecycle = "PENDING"
    terminal_reason = "FOLLOW_THROUGH_ABSENT"

    for offset, bar in enumerate(post, start=1):
        close = _num(bar.get("close"))
        candle_id = _bar_id(bar)
        if close is None:
            continue
        if direction == "UP":
            hold = close > level + event_atr * INTERACTION_ATR
            opposite = close < level - event_atr * INTERACTION_ATR
            displacement = (close - level) / event_atr
        else:
            hold = close < level - event_atr * INTERACTION_ATR
            opposite = close > level + event_atr * INTERACTION_ATR
            displacement = (level - close) / event_atr
        meaningful = bool(hold and displacement >= MIN_DISPLACEMENT_ATR)
        if opposite:
            lifecycle = "INVALIDATED"
            terminal_reason = "POST_EVENT_RECLAMATION"
            consecutive = 0
        else:
            consecutive = consecutive + 1 if meaningful else 0
            if consecutive >= CONFIRM_BARS:
                lifecycle = "CONFIRMED"
                terminal_reason = "FOLLOW_THROUGH_CONFIRMED"
        checks.append({"index": idx + offset, "candle_id": candle_id, "close": close, "hold": hold, "displacement_atr": round(displacement, 6), "meaningful": meaningful, "consecutive": consecutive, "terminal": lifecycle if lifecycle in TERMINAL else None})
        if lifecycle in TERMINAL:
            break

    if lifecycle == "PENDING" and age >= FOLLOW_WINDOW:
        lifecycle = "EXPIRED"
        terminal_reason = "EVENT_EXPIRED"

    out = dict(output)
    out["auction_state"] = lifecycle
    out["auction_phase"] = lifecycle
    out["event_age_bars"] = age
    out["event_index"] = idx
    out["follow_through_bars"] = consecutive
    out["required_confirmation_bars"] = CONFIRM_BARS
    out["confirmation_horizon"] = FOLLOW_WINDOW
    out["follow_through_checks"] = checks
    out["auction_lifecycle_repaired"] = True
    out["auction_lifecycle_repair_version"] = VERSION
    out["auction_lifecycle_repair_reason"] = terminal_reason
    if lifecycle == "CONFIRMED":
        out["directional_implication"] = "UP" if direction == "UP" else "DOWN"
        out["auction_confirmation"] = "FOLLOW_THROUGH_CONFIRMED"
    elif lifecycle == "INVALIDATED":
        out["directional_implication"] = "NEUTRAL"
        out["auction_confirmation"] = "POST_EVENT_RECLAMATION"
    else:
        out["directional_implication"] = "NEUTRAL"
    reasons = [str(x) for x in list(out.get("reason_codes") or out.get("reasons") or []) if str(x)]
    code = "E4_EVENT_AGE_REPAIRED" if lifecycle == "PENDING" else f"E4_AUCTION_{lifecycle}"
    if code not in reasons:
        reasons.append(code)
    out["reason_codes"] = reasons
    out["reasons"] = reasons
    return out


def install(pipeline_module: Any) -> None:
    if getattr(pipeline_module, "_E4_EVENT_LIFECYCLE_SURGERY_INSTALLED", False):
        return
    original = pipeline_module.analyze_e4

    def patched_analyze_e4(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
        result = original(snapshot, upstream)
        if not isinstance(result, EngineResult):
            return result
        bars = snapshot.get("bars") if isinstance(snapshot, dict) else None
        bars = [bar for bar in (bars or []) if isinstance(bar, dict)]
        current_candle = snapshot.get("candle_close_timestamp") or snapshot.get("candle") if isinstance(snapshot, dict) else None
        original_output = _out(result)
        repaired = _repair(original_output, bars, current_candle)
        if repaired == original_output:
            print(
                f"[PRODUCTION V2] E4_EVENT_LIFECYCLE_SURGERY version={VERSION} action=SKIP "
                f"state={original_output.get('auction_state')} event_candle={_event_candle_id(original_output, original_output.get('event') or {})} "
                f"bars={len(bars)}",
                flush=True,
            )
            return result
        print(
            f"[PRODUCTION V2] E4_EVENT_LIFECYCLE_SURGERY version={VERSION} action=REPAIR "
            f"state={repaired.get('auction_state')} age={repaired.get('event_age_bars')} "
            f"event_candle={repaired.get('event_candle_id')} reason={repaired.get('auction_lifecycle_repair_reason')}",
            flush=True,
        )
        return EngineResult(result.engine_id, result.name, result.gate_passed, result.score, repaired, result.reason_codes)

    pipeline_module.analyze_e4 = patched_analyze_e4
    pipeline_module._E4_EVENT_LIFECYCLE_SURGERY_INSTALLED = True
