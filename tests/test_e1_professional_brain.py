from production_v2.e1_brain import analyze_e1


def _bars_from_closes(closes, spread=0.08):
    bars = []
    previous = closes[0]
    for i, close in enumerate(closes):
        high = max(previous, close) + spread
        low = min(previous, close) - spread
        bars.append({
            "open": previous,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1000,
            "timestamp": i,
        })
        previous = close
    return bars


def test_e1_does_not_flip_an_established_trend_on_one_abrupt_counter_move():
    closes = [100 + 0.25 * i for i in range(78)]
    closes.extend([119.25, 117.0])
    out = analyze_e1(_bars_from_closes(closes, spread=0.10))
    assert out["trend_state"] in {"UP", "NONE"}
    assert out["market_state"] in {"TREND_UP", "TRANSITION", "UNCLEAR"}
    assert "trend_persistence" in out["professional_reasoning"]


def test_e1_distinguishes_directional_trend_from_volatility_expansion():
    closes = [120 - 0.35 * i for i in range(80)]
    closes[-1] -= 1.5
    out = analyze_e1(_bars_from_closes(closes, spread=0.20))
    assert out["trend_state"] == "DOWN"
    assert out["directional_pressure"] == "DOWN"
    assert out["market_state"] == "TREND_DOWN"
    assert out["volatility_state"] == "EXPANDING"
    assert out["professional_reasoning"]["primary_state"] == "TREND_DOWN"


def test_e1_detects_conflict_as_transition_instead_of_forcing_a_direction():
    closes = [100 + 0.35 * i for i in range(50)] + [117 - 0.65 * (i - 49) for i in range(30)]
    out = analyze_e1(_bars_from_closes(closes))
    assert out["market_state"] == "TRANSITION"
    assert out["transition"] == "PRESENT"
    assert out["professional_reasoning"]["conflict_detected"] is True
    assert out["conflicts"]


def test_e1_reasoning_is_state_analysis_only_and_preserves_evidence_hierarchy():
    closes = [100 + 0.25 * i for i in range(80)]
    out = analyze_e1(_bars_from_closes(closes))
    reasoning = out["professional_reasoning"]
    assert reasoning["task"] == "DESCRIBE_MARKET_STATE_ONLY"
    assert reasoning["evidence_hierarchy"] == (
        "DATA_QUALITY -> VOLATILITY -> STRUCTURE -> PRESSURE -> "
        "PERSISTENCE -> STATE -> TRANSITION"
    )
    assert out["trade_decision_authority"] is False
    assert out["decision_authority"] == "E9_ONLY"
    assert "decision" not in out


def test_e1_confidence_degrades_when_evidence_disagrees():
    trend = [100 + 0.30 * i for i in range(80)]
    conflict = [100 + 0.30 * i for i in range(50)] + [115 - 0.55 * (i - 49) for i in range(30)]
    trend_out = analyze_e1(_bars_from_closes(trend))
    conflict_out = analyze_e1(_bars_from_closes(conflict))
    assert conflict_out["confidence"] < trend_out["confidence"]
