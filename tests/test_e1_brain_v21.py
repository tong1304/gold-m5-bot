# E1 professional-state acceptance contract; intentionally independent of E2-E9.
from production_v2.e1_brain import analyze_e1
from production_v2.e1_brain import MARKET_STATES


def _bars_from_closes(closes, spread=0.08):
    bars = []
    previous = closes[0]
    for i, close in enumerate(closes):
        high = max(previous, close) + spread
        low = min(previous, close) - spread
        bars.append({"open": previous, "high": high, "low": low, "close": close, "volume": 1000, "timestamp": i})
        previous = close
    return bars


def test_e1_is_market_state_only_and_never_authorizes_trade():
    out = analyze_e1(_bars_from_closes([100 + 0.30 * i for i in range(80)]))
    assert out["question"] == "What is the market doing right now?"
    assert out["reasoning_role"] == "MARKET_STATE_ANALYST"
    assert out["trade_decision_authority"] is False
    assert out["decision_authority"] == "E9_ONLY"
    assert "decision" not in out
    assert out["analysis_status"] == "COMPLETE"


def test_e1_requires_reliable_history_before_classification():
    out = analyze_e1(_bars_from_closes([100 + i for i in range(20)]))
    assert out["analysis_status"] == "INCOMPLETE"
    assert out["market_state"] == "UNCLEAR"
    assert out["confidence"] == 0.0


def test_e1_balanced_market_is_not_forced_into_a_direction():
    closes = [100.0]
    for i in range(80):
        closes.append(closes[-1] + (0.20 if i % 2 == 0 else -0.20))
    out = analyze_e1(_bars_from_closes(closes))
    assert out["directional_pressure"] == "NEUTRAL"
    assert out["market_state"] in {"RANGE", "COMPRESSION", "UNCLEAR"}


def test_e1_established_trend_requires_coherent_directional_evidence():
    out = analyze_e1(_bars_from_closes([100 + 0.30 * i for i in range(80)]))
    assert out["market_state"] == "TREND_UP"
    assert out["trend_state"] == "UP"
    assert out["directional_pressure"] == "BULLISH"
    assert out["professional_reasoning"]["trend_maturity"] == "ESTABLISHED"
    assert out["professional_reasoning"]["directional_consensus"]["confirmed"] is True


def test_e1_short_impulse_is_not_labeled_developing_regime():
    closes = [100.0]
    for _ in range(60):
        closes.append(closes[-1] + (0.08 if len(closes) % 2 else -0.08))
    for _ in range(3):
        closes.append(closes[-1] + 0.55)
    out = analyze_e1(_bars_from_closes(closes, spread=0.10))
    assert out["market_state"] in MARKET_STATES
    assert out["market_state"] != "DEVELOPING"
    assert out["professional_reasoning"]["trend_maturity"] != "DEVELOPING"


def test_e1_one_counter_candle_does_not_reverse_established_regime():
    closes = [100 + 0.25 * i for i in range(78)] + [119.25, 117.0]
    out = analyze_e1(_bars_from_closes(closes, spread=0.10))
    assert out["trend_state"] in {"UP", "NONE"}
    assert out["market_state"] in {"TREND_UP", "TRANSITION", "UNCLEAR"}


def test_e1_conflict_becomes_transition_not_forced_trend():
    closes = [100 + 0.35 * i for i in range(50)] + [117 - 0.65 * (i - 49) for i in range(30)]
    out = analyze_e1(_bars_from_closes(closes))
    assert out["market_state"] == "TRANSITION"
    assert out["transition"] == "PRESENT"
    assert out["professional_reasoning"]["conflict_detected"] is True
    assert out["conflicts"]


def test_e1_keeps_liquidity_analysis_out_of_market_state_ownership():
    out = analyze_e1(_bars_from_closes([100 + 0.25 * i for i in range(80)]))
    evidence = out["professional_reasoning"]["independent_evidence"]
    assert "liquidity_event" not in evidence
    assert "liquidity" not in out["professional_reasoning"]["ownership_boundaries"]
