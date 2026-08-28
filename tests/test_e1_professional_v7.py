from production_v2.e1_professional_layer_v7 import _dominant_direction, _phase


def _bars_from_closes(closes):
    bars = []
    for i, close in enumerate(closes):
        prev = closes[i - 1] if i else close
        bars.append({"open": prev, "high": max(prev, close) + 0.1, "low": min(prev, close) - 0.1, "close": close})
    return bars


def test_structure_and_ema_alignment_dominates_counter_pressure():
    direction, basis = _dominant_direction(
        ema_direction="DOWN",
        structure_direction="DOWN",
        slope20=-0.05,
        slope40=-3.1,
        ema_gap_atr=-1.3,
    )
    assert direction == "DOWN"
    assert basis == "STRUCTURE_EMA_ALIGNMENT"


def test_mixed_structure_does_not_create_trend_from_ema_alone_without_long_alignment():
    direction, basis = _dominant_direction(
        ema_direction="DOWN",
        structure_direction="NEUTRAL",
        slope20=-0.10,
        slope40=-0.20,
        ema_gap_atr=-1.0,
    )
    assert direction == "NEUTRAL"
    assert basis == "NO_DOMINANT_DIRECTION"


def test_pullback_is_phase_not_reversal():
    bars = _bars_from_closes([110, 109, 108, 107, 105])
    phase, basis = _phase(bars, "DOWN", 1.0)
    assert phase == "IMPULSE"
    assert basis == "RECENT_PRESSURE_ALIGNS_WITH_TREND"

    bars = _bars_from_closes([105, 106, 107, 108, 109])
    phase, basis = _phase(bars, "DOWN", 1.0)
    assert phase == "PULLBACK"
    assert basis == "RECENT_PRESSURE_COUNTERS_DOMINANT_TREND"
