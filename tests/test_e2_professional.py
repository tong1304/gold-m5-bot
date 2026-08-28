from production_v2.e2_brain import analyze_e2


def _snapshot(n=120):
    bars = []
    price = 100.0
    for i in range(n):
        drift = 0.18 if i > 70 else 0.03
        open_ = price
        close = price + drift
        high = close + 0.12
        low = open_ - 0.08
        bars.append({"open": open_, "high": high, "low": low, "close": close})
        price = close
    return {"bars": bars, "E1_result": {"finding": "MARKET_STATE=RANGE"}}


def test_e2_exposes_professional_reasoning_contract_without_entry_authority():
    result = analyze_e2(_snapshot())

    assert result["reasoning_mode"] == "PROFESSIONAL_DISCRETIONARY"
    assert result["trade_decision_authority"] == "NONE"
    assert result["independence"] == "E2_INDEPENDENT_E1_CROSS_CHECK"
    assert isinstance(result["opportunity_taxonomy"], list)
    assert isinstance(result["opportunity_hierarchy"]["ranked"], list)
    assert isinstance(result["conditional_map"], list)
    assert isinstance(result["hard_veto"], list)
    assert "primary_thesis" in result
    assert "counter_evidence" in result
    assert "invalidation" in result


def test_e2_never_returns_entry_or_final_trade_decision():
    result = analyze_e2(_snapshot())

    assert result["entry"] is None
    assert result["decision"] is None
    assert result["trade_decision_authority"] == "NONE"


def test_e2_has_explicit_no_trade_path_when_opportunity_is_unproven():
    result = analyze_e2(_snapshot())

    assert result["no_trade_reasoning"]
    assert result["conditional_map"]
    assert all("IF" in item["if"] and "THEN" in item["then"] for item in result["conditional_map"])
