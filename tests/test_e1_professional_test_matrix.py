"""Professional E1 acceptance matrix.

E1 is tested as a market-state analyst only. The matrix deliberately tests
classification, evidence hierarchy, conflict handling, uncertainty, and
ownership boundaries without asserting any trade decision.
"""

from math import sin

import pytest

from production_v2.e1_brain import MARKET_STATES, analyze_e1


def _bars_from_closes(closes, spread=0.08):
    bars = []
    previous = closes[0]
    for i, close in enumerate(closes):
        high = max(previous, close) + spread
        low = min(previous, close) - spread
        bars.append({"open": previous, "high": high, "low": low, "close": close, "volume": 1000, "timestamp": i})
        previous = close
    return bars


def _uptrend():
    return _bars_from_closes([100.0 + 0.30 * i for i in range(100)])


def _downtrend():
    return _bars_from_closes([200.0 - 0.30 * i for i in range(100)])


def _range():
    closes = [100.0]
    for i in range(100):
        closes.append(closes[-1] + (0.20 if i % 2 == 0 else -0.20))
    return _bars_from_closes(closes)


def _compression():
    closes = [100.0]
    for i in range(70):
        closes.append(closes[-1] + (0.20 if i % 2 == 0 else -0.20))
    for i in range(30):
        closes.append(closes[-1] + (0.025 if i % 2 == 0 else -0.025))
    bars = _bars_from_closes(closes, spread=0.08)
    for bar in bars[-30:]:
        bar["high"] = max(bar["open"], bar["close"]) + 0.012
        bar["low"] = min(bar["open"], bar["close"]) - 0.012
    return bars


def _expanding_directional_move():
    closes = [100.0]
    for i in range(100):
        step = 0.10 + (0.035 * max(0, i - 80))
        closes.append(closes[-1] + step)
    return _bars_from_closes(closes, spread=0.08)


def _transition():
    closes = []
    price = 100.0
    for i in range(100):
        price += 0.25 if i < 65 else -0.85
        closes.append(price)
    return _bars_from_closes(closes, spread=0.10)


def _clean_bear_trend():
    closes = [200.0 - 0.55 * i + 0.90 * sin(i * 0.70) for i in range(120)]
    return _bars_from_closes(closes)


@pytest.mark.parametrize(
    "name,bars,expected_state,expected_pressure,expected_trend",
    [
        ("clean_uptrend", _uptrend(), "TREND_UP", "BULLISH", "UP"),
        ("clean_downtrend", _downtrend(), "TREND_DOWN", "BEARISH", "DOWN"),
        ("balanced_range", _range(), "RANGE", "NEUTRAL", "NONE"),
        ("tight_compression", _compression(), "COMPRESSION", "NEUTRAL", "NONE"),
        ("horizon_transition", _transition(), "TRANSITION", "BEARISH", "NONE"),
    ],
)
def test_matrix_primary_market_states(name, bars, expected_state, expected_pressure, expected_trend):
    out = analyze_e1(bars)
    assert out["market_state"] == expected_state, name
    assert out["directional_pressure"] == expected_pressure, name
    assert out["trend_state"] == expected_trend, name
    assert out["market_state"] in MARKET_STATES
    assert out["analysis_status"] == "COMPLETE"
    assert out["professional_reasoning"]["primary_state"] == out["market_state"]


def test_matrix_expansion_is_volatility_information_not_automatic_trade_state():
    out = analyze_e1(_expanding_directional_move())
    assert out["volatility_state"] in {"EXPANDING", "NORMAL"}
    assert out["market_state"] in MARKET_STATES
    assert "decision" not in out


def test_matrix_insufficient_history_withholds_classification():
    out = analyze_e1(_bars_from_closes([100.0 + i for i in range(59)]))
    assert out["analysis_status"] == "INCOMPLETE"
    assert out["market_state"] == "UNCLEAR"
    assert out["confidence"] == 0.0
    assert out["trade_decision_authority"] is False


def test_matrix_invalid_data_is_not_silently_accepted():
    bars = _uptrend()
    bars[20] = {"open": 100, "high": 90, "low": 95, "close": 92}
    out = analyze_e1(bars)
    assert "DATA_QUALITY_ANOMALIES" in out["conflicts"]
    assert out["analysis_status"] == "COMPLETE"


def test_matrix_ema_price_pressure_conflict_is_explicit():
    closes = [100.0 + 0.28 * i for i in range(65)]
    closes.extend([closes[-1] - 0.75 * i for i in range(1, 36)])
    out = analyze_e1(_bars_from_closes(closes))
    assert "EMA_VS_PRICE_PRESSURE" in out["conflicts"] or out["market_state"] == "TRANSITION"
    assert out["professional_reasoning"]["conflict_detected"] is True
    assert out["professional_reasoning"]["trend_confirmed"] is False


def test_matrix_structure_pressure_conflict_cannot_be_promoted_to_confirmed_trend():
    closes = [100.0 + 0.35 * i for i in range(60)]
    closes.extend([closes[-1] - 0.50 * i for i in range(1, 41)])
    out = analyze_e1(_bars_from_closes(closes))
    if "STRUCTURE_VS_PRICE_PRESSURE" in out["conflicts"]:
        assert out["professional_reasoning"]["trend_confirmed"] is False
        assert out["market_state"] != "TREND_UP"


def test_matrix_long_horizon_conflict_is_transition():
    result = analyze_e1(_clean_bear_trend())
    assert result["market_state"] == "TREND_DOWN"
    result = analyze_e1(_transition())
    assert result["market_state"] == "TRANSITION"
    assert result["transition"] == "PRESENT"
    assert result["professional_reasoning"]["trend_confirmed"] is False


def test_matrix_transition_is_not_a_reversal_signal():
    out = analyze_e1(_transition())
    assert out["market_state"] == "TRANSITION"
    assert out["trend_state"] == "NONE"
    assert out["transition"] == "PRESENT"
    assert "decision" not in out


def test_matrix_e1_ownership_is_strict():
    out = analyze_e1(_uptrend())
    assert out["trade_decision_authority"] is False
    assert out["decision_authority"] == "E9_ONLY"
    forbidden_keys = {"decision", "entry", "stop", "target", "position_size", "execution"}
    assert not forbidden_keys.intersection(out.keys())
    owned = out["professional_reasoning"]["ownership_boundaries"]["owns"]
    not_owned = out["professional_reasoning"]["ownership_boundaries"]["does_not_own"]
    assert "market_regime" in owned
    assert "entry_confirmation" in not_owned
    assert "trade_execution" in not_owned


def test_matrix_evidence_hierarchy_is_preserved():
    out = analyze_e1(_uptrend())
    reasoning = out["professional_reasoning"]
    assert reasoning["task"] == "DESCRIBE_MARKET_STATE_ONLY"
    assert out["reasoning_role"] == "MARKET_STATE_ANALYST"
    assert out["reasoning_trace"]
    assert "QUESTION -> What is the market doing right now?" in out["reasoning_trace"][0]
    assert reasoning["ownership_boundaries"]["owns"]


def test_matrix_same_input_is_deterministic():
    bars = _uptrend()
    first = analyze_e1(bars)
    second = analyze_e1(bars)
    assert first == second


def test_matrix_professional_states_are_closed_vocabulary():
    cases = [_uptrend(), _downtrend(), _range(), _compression(), _transition(), _expanding_directional_move()]
    for bars in cases:
        out = analyze_e1(bars)
        assert out["market_state"] in MARKET_STATES
        assert out["trend_state"] in {"UP", "DOWN", "NONE"}
        assert out["directional_pressure"] in {"BULLISH", "BEARISH", "NEUTRAL"}
        assert out["volatility_state"] in {"EXPANDING", "CONTRACTING", "NORMAL", "UNKNOWN"}
        assert out["transition"] in {"PRESENT", "ABSENT", "UNKNOWN"}


def test_matrix_no_e1_output_can_authorize_a_trade():
    for bars in (_uptrend(), _downtrend(), _range(), _transition()):
        out = analyze_e1(bars)
        assert out["trade_decision_authority"] is False
        assert out["decision_authority"] == "E9_ONLY"
        assert "decision" not in out
