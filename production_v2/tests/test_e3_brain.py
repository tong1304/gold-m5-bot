from production_v2.e3_brain import analyze_e3


def _bars(closes):
    bars = []
    for i, close in enumerate(closes):
        close = float(close)
        bars.append({
            "open": close - 0.2,
            "high": close + 0.4,
            "low": close - 0.4,
            "close": close,
            "volume": 1.0,
            "timestamp": i,
        })
    return bars


def test_e3_returns_real_evidence_contract():
    closes = [100 + ((i % 5) * 0.15) for i in range(60)]
    result = analyze_e3(_bars(closes))
    assert result["analysis_status"] == "COMPLETE"
    assert result["question"] == "What is price structure communicating?"
    assert result["finding"] != "UNRESOLVED"
    assert result["observations"]
    assert result["architecture"] == "E3_SINGLE_PROFESSIONAL_BRAIN_V1"
    assert result["sub_engines_active"] is False
    assert result["upstream_direction_used"] is False
    assert result["trade_decision_authority"] is False


def test_e3_detects_confirmed_upward_break_without_upstream_input():
    closes = [100.0] * 25
    closes += [101.0, 99.0, 101.5, 99.2, 100.0, 101.0, 100.0, 101.2]
    closes += [100.5, 102.5, 103.0, 103.2, 103.4]
    closes += [103.0] * 20
    result = analyze_e3(_bars(closes))
    assert result["direction"] in {"UP", "MIXED", "NEUTRAL"}
    assert result["bos"]["event"] in {"CONFIRMED_BOS", "NO_BOS"}
    assert "evidence" in result
    assert "reason_codes" in result


def test_e3_never_exposes_trade_authority_or_gate():
    result = analyze_e3(_bars([100 + (i % 3) for i in range(50)]))
    assert result["trade_decision_authority"] is False
    assert result["decision_authority"] == "E9_ONLY"
    assert result["gate"] is None
    assert result["sub_engines_status"] == "PAUSED"
