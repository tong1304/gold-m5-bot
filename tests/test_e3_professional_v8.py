from production_v2.e3_brain_v8 import DOWN, NEUTRAL, UP, _break


def bar(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c}


def test_wick_only_break_is_not_confirmed():
    result = _break(bar(100, 102, 99, 100.2), 101, UP, 2.0)
    assert result["confirmed"] is False
    assert result["direction"] == NEUTRAL


def test_closed_candle_displacement_confirms_up_break():
    result = _break(bar(100, 103, 99.5, 102.8), 101, UP, 2.0)
    assert result["confirmed"] is True
    assert result["direction"] == UP
    assert result["close_beyond_level"] is True
    assert result["displacement_ok"] is True


def test_closed_candle_displacement_confirms_down_break():
    result = _break(bar(100, 100.5, 96, 96.8), 99, DOWN, 2.0)
    assert result["confirmed"] is True
    assert result["direction"] == DOWN
    assert result["close_beyond_level"] is True


def test_close_must_clear_level_by_atr_buffer():
    result = _break(bar(100, 101.2, 99, 101.1), 101, UP, 2.0)
    assert result["close_beyond_level"] is False
    assert result["confirmed"] is False


def test_e3_is_analysis_only_contract():
    import production_v2.e3_brain_v8 as e3
    assert e3.ARCHITECTURE == "E3_SINGLE_PROFESSIONAL_BRAIN_V8"
    assert e3.QUESTION == "What is price structure communicating?"
