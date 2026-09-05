from __future__ import annotations

from typing import Any

from .contracts import EngineResult

VERSION = "E4_EVENT_LIFECYCLE_SURGERY_V1"
CONFIRM_BARS = 2
FOLLOW_WINDOW = 5
INTERACTION_ATR = 0.05
MIN_DISPLACEMENT_ATR = 0.20
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


def _event_index(output: dict[str, Any], bars: list[dict[str, Any]]) -> int:
    event = output.get("event") if isinstance(output.get("event"), dict) else {}
    candle_id = str(output.get("event_candle_id") or event.get("event_candle_id") or "")
    if candle_id:
        for i, bar in enumerate(bars):
            if _bar_id(bar) == candle_id:
                return i
    try:
        idx = int(event.get("index", output.get("event_index", -1)))
        if 0 <= idx < len(bars):
            return idx
    except (TypeError, ValueError):
        pass
    return -1


def _direction(output: dict[str, Any], event: dict[str, Any]) -> str:
    value = _text(event.get("directional_implication") or output.get("directional_implication") or output.get("direction"))
    if value in {"UP", "BUY", "BULLISH"}: return "UP"
    if value in {"DOWN", "SELL", "BEARISH"}: return "DOWN"
    return "NEUTRAL"


def _level(output: dict[str, Any], event: dict[str, Any]) -> float | None:
    return _num(output.get("event_level")) if _num(output.get("event_level")) is not None else _num(event.get("event_level"))


def _event_atr(output: dict[str, Any], event: dict[str, Any]) -> float:
    return _num(event.get("event_atr") or output.get("event_atr") or output.get("atr14_current")) or 0.0


def _repair(output: dict[str, Any], bars: list[dict[str, Any]]) -> dict[str, Any]:
    event = output.get("event") if isinstance(output.get("event"), dict) else {}
    state = _text(output.get("auction_state") or output.get("auction_phase") or output.get("state"))
    if state not in {"PENDING", "DEVELOPING", "FORMING", "AWAITING_CONFIRMATION", "CONFIRMATION_PENDING"}:
        return output
    idx = _event_index(output, bars)
    if idx < 0 or idx >= len(bars) - 1:
        return output
    direction = _direction(output, event)
    level = _level(output, event)
    event_atr = _event_atr(output, event)
    if direction == "NEUTRAL" or level is None or event_atr <= 0:
        return output

    post = bars[idx + 1:]
    age = len(post)
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

    if lifecycle == "PENDING" and age == 0:
        return output

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
    reasons = list(out.get("reason_codes") or out.get("reasons") or [])
    reasons = [str(x) for x in reasons if str(x)]
    for code in (["E4_EVENT_AGE_REPAIRED"] if lifecycle == "PENDING" else [f"E4_AUCTION_{lifecycle}"]):
        if code not in reasons: reasons.append(code)
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
        repaired = _repair(_out(result), bars)
        if repaired == result.output:
            return result
        print(
            f"[PRODUCTION V2] E4_EVENT_LIFECYCLE_SURGERY version={VERSION} "
            f"state={repaired.get('auction_state')} age={repaired.get('event_age_bars')} "
            f"reason={repaired.get('auction_lifecycle_repair_reason')}",
            flush=True,
        )
        return EngineResult(result.engine_id, result.name, result.gate_passed, result.score, repaired, result.reason_codes)

    pipeline_module.analyze_e4 = patched_analyze_e4
    pipeline_module._E4_EVENT_LIFECYCLE_SURGERY_INSTALLED = True
