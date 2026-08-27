from production_v2.professional_e4_brain import analyze_e4


def _base_bars(n=70):
    bars = []
    price = 100.0
    for i in range(n):
        drift = 0.15 if i % 7 < 4 else -0.10
        open_ = price
        close = price + drift
        high = max(open_, close) + 0.35
        low = min(open_, close) - 0.35
        bars.append({"open": open_, "high": high, "low": low, "close": close})
        price = close
    return bars


def _high_liquidity_sweep_bars():
    bars = _base_bars(65)
    # Create repeated highs that form a liquidity pool.
    for idx in (50, 54):
        bars[idx]["high"] = 112.0
        bars[idx]["close"] = 111.4
    # Final candle raids the equal highs and closes back below them with a clear upper wick.
    bars[-1] = {
        "open": 111.8,
        "high": 112.9,
        "low": 111.0,
        "close": 111.5,
    }
    return bars


def test_e4_accepts_pipeline_snapshot_without_losing_closed_candle_data():
    result = analyze_e4({"bars": _base_bars()})

    assert result["analysis_status"] == "COMPLETE"
    assert result["reasoning_role"] == "LIQUIDITY_AUCTION_ANALYST"
    assert result["trade_decision_authority"] is False
    assert result["decision"] is None
    assert result["gate"] is None


def test_e4_detects_liquidity_sweep_and_rejection_from_price_action():
    result = analyze_e4({"bars": _high_liquidity_sweep_bars()})

    assert result["finding"] == "HIGH_SWEEP_REJECTION"
    assert result["auction_state"] == "REJECTION"
    assert result["directional_implication"] == "DOWN"
    assert result["liquidity_state"] == "TAKEN"
    assert result["evidence_strength"] >= 0.90


def test_e4_never_consumes_upstream_decision_gate_or_score():
    result = analyze_e4(
        {"bars": _base_bars()},
        {
            "E1": {"evidence": {"output": {"direction": "UP", "decision": "BUY", "score": 99, "gate": True}}},
            "E2": {"evidence": {"output": {"direction": "UP", "decision": "BUY", "score": 98, "gate": True}}},
            "E3": {"evidence": {"output": {"direction": "UP", "decision": "BUY", "score": 97, "gate": True}}},
        },
    )

    reasoning = result["professional_reasoning"]
    assert reasoning["context_corrobation_only"] is True
    assert reasoning["context_used"] is True
    assert reasoning["decisions_used"] is False
    assert reasoning["gates_used"] is False
    assert reasoning["scores_used"] is False
