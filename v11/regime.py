from __future__ import annotations

import math
import pandas as pd

from .common import num, ema, atr14


def _finite(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _atr(frame):
    value = _finite(atr14(frame).iloc[-1]) if len(frame) >= 14 else None
    if value is None or value <= 0:
        value = _finite((frame.high - frame.low).tail(14).mean())
    return value if value is not None and value > 0 else None


def _direction(m15: pd.DataFrame) -> str:
    x = m15.tail(100).reset_index(drop=True)
    if len(x) < 60:
        return "NEUTRAL"
    e20 = _finite(ema(x, 20).iloc[-1])
    e50 = _finite(ema(x, 50).iloc[-1])
    close = _finite(x.close.iloc[-1])
    if e20 is None or e50 is None or close is None:
        return "NEUTRAL"
    if close > e20 > e50:
        return "BUY"
    if close < e20 < e50:
        return "SELL"
    return "NEUTRAL"


def build_regime_context(m5: pd.DataFrame, m15: pd.DataFrame) -> dict:
    """Build deterministic, price-normalized evidence for V11 strategies.

    The helper intentionally does not produce a composite score.  Each strategy
    consumes only the fields relevant to its own setup.
    """
    x = m5.tail(80).reset_index(drop=True).copy()
    atr = _atr(x)
    close = _finite(x.close.iloc[-1]) if len(x) else None
    high = pd.to_numeric(x.high, errors="coerce") if len(x) else pd.Series(dtype=float)
    low = pd.to_numeric(x.low, errors="coerce") if len(x) else pd.Series(dtype=float)

    recent_range = _finite((high.tail(12).max() - low.tail(12).min())) if len(x) else None
    prior_range = _finite((high.iloc[-36:-12].max() - low.iloc[-36:-12].min())) if len(x) >= 36 else None
    range_ratio = recent_range / atr if recent_range is not None and atr else None
    compression_ratio = recent_range / prior_range if recent_range is not None and prior_range and prior_range > 0 else None

    e20 = _finite(ema(x, 20).iloc[-1]) if len(x) else None
    trend_strength = abs(close - e20) / atr if close is not None and e20 is not None and atr else None

    typical = (pd.to_numeric(x.high, errors="coerce") + pd.to_numeric(x.low, errors="coerce") + pd.to_numeric(x.close, errors="coerce")) / 3
    volume = pd.to_numeric(x.get("volume", pd.Series(1.0, index=x.index)), errors="coerce").fillna(1.0).clip(lower=1e-9)
    if "datetime" in x:
        ts = pd.to_datetime(x["datetime"], errors="coerce", utc=True)
        vwap_series = (typical * volume).groupby(ts.dt.date).cumsum() / volume.groupby(ts.dt.date).cumsum()
    else:
        vwap_series = (typical * volume).cumsum() / volume.cumsum()
    vwap = _finite(vwap_series.iloc[-1]) if len(vwap_series) else None
    vwap_distance_atr = abs(close - vwap) / atr if close is not None and vwap is not None and atr else None

    body_ratio = upper_wick_ratio = lower_wick_ratio = None
    if len(x):
        row = x.iloc[-1]
        o, h, l, c = map(float, (row.open, row.high, row.low, row.close))
        candle_range = max(h - l, 1e-12)
        body_ratio = _finite(abs(c - o) / candle_range)
        upper_wick_ratio = _finite((h - max(o, c)) / candle_range)
        lower_wick_ratio = _finite((min(o, c) - l) / candle_range)

    return {
        "m15_direction": _direction(m15),
        "atr": atr,
        "range_ratio": range_ratio,
        "compression_ratio": compression_ratio,
        "trend_strength": trend_strength,
        "vwap": vwap,
        "vwap_distance_atr": vwap_distance_atr,
        "body_ratio": body_ratio,
        "upper_wick_ratio": upper_wick_ratio,
        "lower_wick_ratio": lower_wick_ratio,
    }
