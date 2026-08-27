from production_v2.e5_brain import analyze_e5


def _trend_up_snapshot():
    bars = []
    price = 100.0
    for i in range(100):
        # Controlled bullish auction with the latest candles extended from value.
        step = 0.20 if i < 80 else 0.65
        o = price
        c = price + step
        bars.append({"open": o, "high": c + 0.08, "low": o - 0.05, "close": c, "volume": 1000 + i})
        price = c
    return {
        "bars": bars,
    }, {
        "E1": {"evidence": {"market_state": "TREND_UP", "structure": "BULLISH", "pressure": "BULLISH"}},
        "E2": {"evidence": {"thesis": "TREND/UP", "opportunity": "TREND_PULLBACK_CONTINUATION"}},
        "E3": {"evidence": {"structure": "EXTERNAL_UP_INTERNAL_UP"}},
        "E4": {"evidence": {"liquidity": "HIGH_ACCEPTANCE_CANDIDATE", "taker": "BUYERS"}},
    }


def test_e5_does_not_prefer_countertrend_short_just_because_price_is_premium():
    snapshot, permitted = _trend_up_snapshot()
    result = analyze_e5(snapshot, permitted)

    assert result["preferred_location"] != "SHORT"
    assert "COUNTERTREND_LOCATION" not in result["reason_codes"]


def test_e5_marks_extended_aligned_market_as_wait_for_repricing():
    snapshot, permitted = _trend_up_snapshot()
    result = analyze_e5(snapshot, permitted)

    assert result["extension_state"] in {"EXTENDED", "EXCESSIVE"}
    assert result["location_state"] in {"WAIT_REPRICING", "UNFAVORABLE", "BOTH_CONDITIONAL"}
    assert result["professional_reasoning"]["decision_authority"] == "E9_ONLY"


def test_e5_keeps_long_and_short_location_independent_without_entry_authority():
    snapshot, permitted = _trend_up_snapshot()
    result = analyze_e5(snapshot, permitted)

    assert "long_location_quality" in result
    assert "short_location_quality" in result
    assert result["trade_decision_authority"] is False
    assert result["gate"] is None
