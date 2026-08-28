from production_v2.e3_brain import analyze_e3


def bar(open_, high, low, close):
    return {"open": open_, "high": high, "low": low, "close": close}


def series(values, wick=0.2):
    out = []
    for i, close in enumerate(values):
        prev = values[i - 1] if i else close
        out.append(bar(prev, max(prev, close) + wick, min(prev, close) - wick, close))
    return out


def test_current_sweep_reclaim_is_not_reported_as_bos_or_failed_bos():
    bars = series([100 + i * 0.2 for i in range(60)])
    bars[-1] = bar(110.0, 112.0, 109.0, 109.7)
    result = analyze_e3(bars)
    assert result["bos"]["confirmed"] is False
    assert result["failure"]["confirmed"] is False
    assert result["sweep_reclaim"]["confirmed"] is True
    assert result["sweep_reclaim"]["direction"] == "DOWN"


def test_failed_bos_requires_a_real_break_then_closed_reclaim():
    bars = series([100 + i * 0.2 for i in range(58)])
    bars[-2] = bar(111.0, 113.0, 110.5, 112.0)
    bars[-1] = bar(112.0, 112.3, 109.0, 109.4)
    result = analyze_e3(bars)
    assert result["failure"]["confirmed"] is True
    assert result["failure"]["event"] == "FAILED_BOS"
    assert result["break_lifecycle"]["stage"] == "FAILED_BREAK_RECLAIM"


def test_break_lifecycle_does_not_promote_historical_break_to_current_break():
    bars = series([100 + i * 0.2 for i in range(60)])
    result = analyze_e3(bars)
    lifecycle = result["break_lifecycle"]
    assert lifecycle["current"] is False
    assert lifecycle["stage"] in {"NO_CONFIRMED_BREAK", "HISTORICAL_ACCEPTED_BREAK"}


def test_structure_authority_explains_external_priority_and_internal_conflict():
    bars = series([100 + i * 0.5 for i in range(50)])
    result = analyze_e3(bars)
    detail = result["authority_detail"]
    assert "primary" in detail
    assert "external" in detail["primary"].lower()
    assert result["reasoning_trace"]["external_is_authority"] is True
    assert result["reasoning_trace"]["upstream_inputs_used"] is False


def test_structural_invalidation_is_closed_candle_based():
    bars = series([120 - i * 0.4 for i in range(55)])
    result = analyze_e3(bars)
    invalidation = result["structural_invalidation"]
    assert "CLOSED_CANDLE" in invalidation["type"] or invalidation["level"] is None


def test_e3_never_has_trade_decision_authority():
    result = analyze_e3(series([100 + i * 0.3 for i in range(80)]))
    assert result["trade_decision_authority"] is False
    assert result["decision_authority"] == "E9_ONLY"
    assert result["decision"] is None
    assert result["gate"] is None
    assert result["upstream_direction_used"] is False
    assert result["upstream_decisions_used"] is False
