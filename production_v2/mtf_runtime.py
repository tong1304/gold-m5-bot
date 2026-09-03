from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar("production_v2_mtf_context", default=None)
_INSTALLED = False


def _parse_time(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _timestamp(bar: dict[str, Any]) -> str | None:
    value = bar.get("timestamp") or bar.get("time") or bar.get("candle_id")
    return str(value) if value is not None else None


def _closed_m15_from_m5(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate closed M5 bars into complete, aligned M15 context candles."""
    groups: dict[int, list[dict[str, Any]]] = {}
    for bar in bars or []:
        if not isinstance(bar, dict) or bar.get("is_closed") is not True:
            continue
        stamp = _parse_time(_timestamp(bar))
        if stamp is None:
            continue
        epoch = int(stamp.timestamp())
        bucket = epoch - (epoch % 900)
        groups.setdefault(bucket, []).append(bar)

    output: list[dict[str, Any]] = []
    for bucket in sorted(groups):
        group = sorted(groups[bucket], key=lambda item: _parse_time(_timestamp(item)) or datetime.min.replace(tzinfo=timezone.utc))
        if len(group) != 3:
            continue
        stamps = [_parse_time(_timestamp(item)) for item in group]
        if any(stamp is None for stamp in stamps):
            continue
        if any(int(stamp.timestamp()) != bucket + i * 300 for i, stamp in enumerate(stamps)):
            continue
        close_time = stamps[-1].timestamp() + 300
        anchor = datetime.fromtimestamp(bucket, timezone.utc).isoformat().replace("+00:00", "Z")
        output.append({
            "open": float(group[0]["open"]),
            "high": max(float(item["high"]) for item in group),
            "low": min(float(item["low"]) for item in group),
            "close": float(group[-1]["close"]),
            "timestamp": anchor,
            "candle_id": anchor,
            "candle_close_timestamp": datetime.fromtimestamp(close_time, timezone.utc).isoformat().replace("+00:00", "Z"),
            "is_closed": True,
            "timeframe": "M15",
        })
    return output


def _decorate(output: Any, engine_id: str) -> Any:
    if not isinstance(output, dict):
        return output
    context = _CONTEXT.get() or {}
    decorated = dict(output)
    decorated["timeframe"] = "M15" if engine_id in {"E1", "E2"} else "M5"
    decorated["context_timeframe"] = "M15"
    decorated["setup_timeframe"] = "M5"
    decorated["m5_timestamp"] = context.get("m5_timestamp")
    decorated["m15_timestamp"] = context.get("m15_timestamp")
    decorated["snapshot_id"] = context.get("snapshot_id")
    decorated["closed_candle_only"] = True
    decorated["lookahead_allowed"] = False
    return decorated


def _first_blocker(result: Any) -> tuple[str, str]:
    engines = {engine.engine_id: (engine.output or {}) for engine in getattr(result, "engines", ())}
    e6, e7, e8, e9 = engines.get("E6", {}), engines.get("E7", {}), engines.get("E8", {}), engines.get("E9", {})
    decision = str(getattr(result, "decision", "NO_TRADE") or "NO_TRADE").upper()
    if decision in {"BUY", "SELL"} and bool(getattr(result, "gate_passed", False)):
        return "NONE", "TRADE_EXECUTION_APPROVED"
    e6_setup = str(e6.get("setup") or e6.get("setup_family") or "").upper()
    if not e6_setup or e6_setup in {"NO_SETUP", "UNKNOWN", "NONE"}:
        reason = next(iter(e6.get("reason_codes") or e6.get("reasons") or ["NO_SURVIVING_E6_THESIS"]), "NO_SURVIVING_E6_THESIS")
        return "E6", str(reason)
    watch = e6.get("watch_only") is True or e6_setup in {"OPPORTUNITY_WATCH", "OPPORTUNITY_CANDIDATE", "OPPORTUNITY_THESIS"}
    confirmation = str(e7.get("confirmation") or e7.get("confirmation_state") or "").upper()
    if watch or confirmation in {"", "WAIT", "PENDING", "NOT_APPLICABLE", "UNPROVEN"}:
        reason = next(iter(e7.get("reason_codes") or e7.get("reasons") or ["E7_CONFIRMATION_REQUIRED"]), "E7_CONFIRMATION_REQUIRED")
        return "E7", str(reason)
    economic_state = str(e8.get("economic_state") or e8.get("risk_state") or "").upper()
    if economic_state in {"NOT_APPLICABLE", "ECONOMICALLY_INVALID", "INVALID", "BLOCKED"} or e8.get("gate_passed") is False:
        reason = next(iter(e8.get("reason_codes") or e8.get("reasons") or ["E8_ECONOMICS_BLOCKED"]), "E8_ECONOMICS_BLOCKED")
        return "E8", str(reason)
    reason = next(iter(e9.get("reason_codes") or e9.get("decision_reasons") or ["E9_FINAL_GOVERNANCE"]), "E9_FINAL_GOVERNANCE")
    return "E9", str(reason)


def install(pipeline_module, market_data_module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    original_e1 = pipeline_module.analyze_e1
    original_e2 = pipeline_module.analyze_e2
    original_run = pipeline_module.ProductionPipeline.run

    # LiveMarketData is defined in live_data.py. Keep the adapter tolerant of
    # callers that historically passed the normalization-only market_data
    # module, but fail with a clear error instead of an import-time AttributeError.
    live_market_data = getattr(market_data_module, "LiveMarketData", None)
    if live_market_data is None:
        from . import live_data as live_data_module
        live_market_data = live_data_module.LiveMarketData
    original_candles = live_market_data.candles

    def analyze_e1_wrapper(bars):
        context = _CONTEXT.get() or {}
        context_bars = context.get("m15_bars")
        return _decorate(original_e1(context_bars if isinstance(context_bars, list) and context_bars else bars), "E1")

    def analyze_e2_wrapper(snapshot):
        context = _CONTEXT.get() or {}
        context_bars = context.get("m15_bars")
        if isinstance(context_bars, list) and context_bars:
            snapshot = dict(snapshot)
            snapshot["bars"] = context_bars
            snapshot["timeframe"] = "M15"
        return _decorate(original_e2(snapshot), "E2")

    def run_wrapper(self, market_data, *, wait_bars=0, resume_state=None, historical_calibration=None):
        data = dict(market_data)
        m5_bars = list(data.get("bars") or [])
        m15_bars = list(data.get("context_bars_m15") or _closed_m15_from_m5(m5_bars))
        m5_timestamp = data.get("data_cutoff_timestamp") or data.get("candle_close_timestamp") or (_timestamp(m5_bars[-1]) if m5_bars else None)
        m15_timestamp = (m15_bars[-1].get("candle_close_timestamp") if m15_bars else None) or (m15_bars[-1].get("timestamp") if m15_bars else None)
        if m15_timestamp and m5_timestamp:
            m15_dt, m5_dt = _parse_time(m15_timestamp), _parse_time(m5_timestamp)
            if m15_dt and m5_dt and m15_dt > m5_dt:
                m15_bars = [bar for bar in m15_bars if (_parse_time(bar.get("candle_close_timestamp") or bar.get("timestamp")) or m5_dt) <= m5_dt]
                m15_timestamp = (m15_bars[-1].get("candle_close_timestamp") if m15_bars else None)
        snapshot_id = f"{data.get('symbol','UNKNOWN')}|M5|{m5_timestamp}"
        token = _CONTEXT.set({
            "m5_bars": m5_bars,
            "m15_bars": m15_bars,
            "m5_timestamp": m5_timestamp,
            "m15_timestamp": m15_timestamp,
            "snapshot_id": snapshot_id,
        })
        try:
            data["context_bars_m15"] = m15_bars
            data["context_timeframe"] = "M15"
            data["setup_timeframe"] = "M5"
            data["snapshot_id"] = snapshot_id
            data["closed_candle_only"] = True
            data["lookahead_allowed"] = False
            result = original_run(self, data, wait_bars=wait_bars, resume_state=resume_state, historical_calibration=historical_calibration)
            risk = dict(getattr(result, "risk", {}) or {})
            authority, reason = _first_blocker(result)
            risk["first_blocking_authority"] = authority
            risk["first_blocking_reason"] = reason
            risk["mtf_contract"] = {
                "context_timeframe": "M15",
                "setup_timeframe": "M5",
                "m5_timestamp": m5_timestamp,
                "m15_timestamp": m15_timestamp,
                "snapshot_id": snapshot_id,
                "closed_candle_only": True,
                "lookahead_allowed": False,
            }
            return result.__class__(result.symbol, result.timeframe, result.decision, result.gate_passed, result.score, result.engines, risk, result.reason_codes)
        finally:
            _CONTEXT.reset(token)

    def candles_wrapper(self, alias: str, limit: int = 200):
        result = original_candles(self, alias, limit=max(limit, 300))
        if not isinstance(result, dict) or not result.get("bars"):
            return result
        result = dict(result)
        bars = list(result.get("bars") or [])
        latest_close = bars[-1].get("candle_close_timestamp")
        if latest_close:
            result["candle_close_timestamp"] = latest_close
            result["data_cutoff_timestamp"] = latest_close
        result["context_bars_m15"] = _closed_m15_from_m5(bars)
        result["context_timeframe"] = "M15"
        result["setup_timeframe"] = "M5"
        result["m5_timestamp"] = result.get("data_cutoff_timestamp") or result.get("candle_close_timestamp") or _timestamp(bars[-1])
        result["m15_timestamp"] = result["context_bars_m15"][-1].get("candle_close_timestamp") if result["context_bars_m15"] else None
        return result

    pipeline_module.analyze_e1 = analyze_e1_wrapper
    pipeline_module.analyze_e2 = analyze_e2_wrapper
    pipeline_module.ProductionPipeline.run = run_wrapper
    live_market_data.candles = candles_wrapper
    _INSTALLED = True
