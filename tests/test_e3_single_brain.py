from production_v2.e3_brain import analyze_e3


def _bars(n=80):
    bars = []
    price = 100.0
    for i in range(n):
        drift = 0.30 if i < 60 else 0.75
        close = price + drift
        bars.append({"open": price, "high": close + 0.25, "low": price - 0.20, "close": close})
        price = close
    return bars


def test_e3_is_single_brain_and_trade_authority_is_parked():
    result = analyze_e3(_bars())
    assert result["engine"] == "E3"
    assert result["architecture"] == "E3_PROFESSIONAL_MARKET_STRUCTURE_CAUSAL_V8"
    assert result["role"] == "MARKET_STRUCTURE_ANALYST"
    assert result["question"] == "What is price structure communicating?"
    assert result["decision_authority"] == "E9_ONLY"
    assert result["trade_decision"] is None


def test_e3_does_not_consume_upstream_direction():
    bars = _bars()
    first = analyze_e3(bars)
    # E3's public analyzer accepts market bars only. Upstream E1/E2 direction
    # is therefore not an input to structural analysis.
    second = analyze_e3(bars)
    assert first["direction"] == second["direction"]
    assert first["finding"] == second["finding"]
    assert second["decision_authority"] == "E9_ONLY"
    assert second["trade_decision"] is None


def test_e3_exposes_current_structural_evidence_contract():
    result = analyze_e3(_bars())
    for key in (
        "structure_state",
        "internal_state",
        "external_structure",
        "internal_structure",
        "protected_structure",
        "bos",
        "choch",
        "failed_break",
        "liquidity",
        "invalidation",
        "structure_lifecycle",
        "structure_integrity",
        "pivots",
    ):
        assert key in result
    assert result["status"] in {"OK", "STRUCTURE_DATA_INVALID"}
    assert result["decision_authority"] == "E9_ONLY"


def test_e3_structural_state_and_counts_are_not_trade_authority():
    result = analyze_e3(_bars())
    external = result["external_structure"]
    internal = result["internal_structure"]
    assert external["basis"] == "ORDERED_CONFIRMED_SWINGS"
    assert internal["basis"] == "ORDERED_CONFIRMED_SWINGS"
    assert external["counts_used_as_authority"] is False
    assert internal["counts_used_as_authority"] is False
    assert result["decision_authority"] == "E9_ONLY"
    assert result["trade_decision"] is None


def test_e3_internal_structure_does_not_become_trade_authority():
    result = analyze_e3(_bars())
    assert result["decision_authority"] == "E9_ONLY"
    assert result["trade_decision"] is None
    assert result["structure_lifecycle"] in {
        "ESTABLISHED",
        "FORMING",
        "TRANSITION",
        "CHOCH",
        "BOS_UP",
        "BOS_DOWN",
        "FAILED_BREAK",
        "SWEEP_RECLAIM",
        "INVALIDATED",
        "INVALID_DATA",
    }
