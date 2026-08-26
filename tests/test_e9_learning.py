from production_v2.e9_learning import (
    build_advisory,
    evaluate_outcome,
    evidence_signature,
    make_decision_record,
)


def test_decision_record_contains_no_future_outcome():
    r = make_decision_record(
        "GOLD", "2026-08-26T05:10:00Z", 4650.0,
        {"decision": "BUY", "thesis_quality": 82},
    )
    assert r.asset == "GOLD"
    assert r.decision == "BUY"
    assert r.outcome is None
    assert r.decision_timestamp == "2026-08-26T05:10:00Z"


def test_signature_is_deterministic():
    evidence = {
        "direction": "BUY",
        "market_state": "TREND_UP",
        "regime": "TREND",
        "setup": "PULLBACK",
        "confirmation": "CONFIRMED",
    }
    assert evidence_signature(evidence) == evidence_signature(dict(evidence))


def test_buy_target_before_stop_is_win():
    candles = [{"high": 101, "low": 99}, {"high": 103, "low": 100}]
    o = evaluate_outcome("BUY", 100, 99, 103, candles, 2)
    assert o.outcome == "WIN"
    assert o.realized_r == 3.0


def test_same_candle_target_and_stop_is_ambiguous():
    candles = [{"high": 104, "low": 98}]
    o = evaluate_outcome("BUY", 100, 99, 103, candles, 1)
    assert o.outcome == "AMBIGUOUS"


def test_advisory_never_overrides_direction():
    advisory = build_advisory("BUY", {"actionable": True, "win_rate": 0.9, "expectancy_r": 1.2})
    assert advisory["role"] == "ADVISORY"
    assert advisory["decision_override"] is False
