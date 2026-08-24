import numpy as np
import pandas as pd

from v11.regime import _classify_m15
from v11.strategy_engine import sort_setup_candidates


def _trend_frame(n=100, slope=0.08):
    base = 100 + np.arange(n) * slope
    wave = 0.45 * np.sin(np.arange(n) * np.pi / 2)
    close = base + wave
    return pd.DataFrame({
        "datetime": pd.date_range("2026-08-25", periods=n, freq="15min", tz="UTC"),
        "open": close - 0.01,
        "high": close + 0.12,
        "low": close - 0.12,
        "close": close,
        "volume": np.full(n, 1000.0),
    })


def test_m15_trend_filter_uses_relaxed_threshold_and_ema20_50():
    result = _classify_m15(_trend_frame())
    assert result["trend_threshold_adx"] == 20
    assert result["trend_ema_alignment"] == "EMA20>EMA50"
    assert result["regime"] == "TREND"


def test_priority_places_e7_and_e4_before_e8():
    candidates = [
        {"engine": "E8", "score_detail": {"score": 100}, "quality": 100},
        {"engine": "E4", "score_detail": {"score": 70}, "quality": 70},
        {"engine": "E7", "score_detail": {"score": 65}, "quality": 65},
    ]
    ordered = sort_setup_candidates(candidates)
    assert [x["engine"] for x in ordered] == ["E7", "E4", "E8"]
