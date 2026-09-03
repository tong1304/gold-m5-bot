from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Callable

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
    return str(bar.get("timestamp") or bar.get("time") or bar.get("candle_id")) if bar.get("timestamp") or bar.get("time") or bar.get("candle_id") else None


def _closed_m15_from_m5(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate closed M5 bars into complete, aligned M15 context candles.

    This derives the exact M15 OHLC from the already frozen M5 snapshot, so the
    context cannot contain a candle newer than the M5 evaluation anchor.
    Incomplete three-bar groups are discarded rather than guessed.
    """
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
        output.append({
            "open": float(group[0]["open"]),
            "high": max(float(item["high"]) for item in group),
            "low": min(float(item["low"]) for item in group),
            "close": float(group[-1]["close"]),
            "timestamp": datetime.fromtimestamp(bucket, timezone.utc).isoformat().replace("+00:00", "Z"),
            "candle_id": datetime.fromtimestamp(bucket, timezone.utc).isoformat().replace("+00:00", "Z"),
            "candle_close_timestamp": datetime.fromtimestamp(close_time, timezone.utc).isoformat().replace("+00:00", "Z"),
            "is_closed": True,
            "timeframe": "M15",
        })
    return output


def _decorate(output: Any, engine_id: str) -> Any:
    if not isinstance(output, dict):
        return output
    context = _CONTEXT.get() or {}
    m5_timestamp = context.get("m5_timestamp")
    m15_timestamp = context.get("m15_timestamp")
    decorated = dict(output)
    decorated["timeframe"] = "M15" if engine_id in {"E1", "E2"} else "M5"
    decorated["context_timeframe"] = "M15"
    decorated["setup_timeframe"] = "M5"
    decorated["m5_timestamp"] = m5_timestamp
    decorated["m15_timestamp"] = m15_timestamp
    decorated["snapshot_id"] = context.get("snapshot_id")
    decorated["closed_candle_only"] = True
    decorated["lookahead_allowed"] = False
    return decorated


def install(pipeline_module, market_data_module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    original_e1 = pipeline_module.analyze_e1
    original_e2 = pipeline_module.analyze_e2
    original_run = pipeline_module.ProductionPipeline.run
    original_candles = market_data_module.LiveMarketData.candles

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
            return original_run(self, data, wait_bars=wait_bars, resume_state=resume_state, historical_calibration=historical_calibration)
        finally:
            _CONTEXT.reset(token)

    def candles_wrapper(self, alias: str, limit: int = 200):
        result = original_candles(self, alias, limit=max(limit, 300))
        if not isinstance(result, dict) or not result.get("bars"):
            return result
        bars = list(result.get("bars") or [])
        result = dict(result)
        result["context_bars_m15"] = _closed_m15_from_m5(bars)
        result["context_timeframe"] = "M15"
        result["setup_timeframe"] = "M5"
        result["m5_timestamp"] = result.get("data_cutoff_timestamp") or result.get("candle_close_timestamp") or _timestamp(bars[-1])
        result["m15_timestamp"] = result["context_bars_m15"][-1].get("candle_close_timestamp") if result["context_bars_m15"] else None
        return result

    pipeline_module.analyze_e1 = analyze_e1_wrapper
    pipeline_module.analyze_e2 = analyze_e2_wrapper
    pipeline_module.ProductionPipeline.run = run_wrapper
    market_data_module.LiveMarketData.candles = candles_wrapper
    _INSTALLED = True
