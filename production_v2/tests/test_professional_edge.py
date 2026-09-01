from production_v2.profit_edge import evaluate_profit_edge
from production_v2.e9_brain import analyze_e9
from production_v2.contracts import EngineResult


def _rows(n=60, win=True, r=1.5):
    return [
        {
            "symbol": "XAUUSD",
            "regime": "TREND_DOWN",
            "direction": "SELL",
            "setup": "TREND_PULLBACK",
            "location": "PREMIUM",
            "confirmation": "CONFIRMED",
            "outcome": "WIN" if win else "LOSS",
            "r_multiple": r if win else -1.0,
        }
        for _ in range(n)
    ]


def test_exact_conditioned_sample_is_trusted_without_relaxation():
    result = evaluate_profit_edge(
        symbol="XAUUSD",
        regime="TREND_DOWN",
        direction="SELL",
        setup="TREND_PULLBACK",
        location="PREMIUM",
        confirmation="CONFIRMED",
        historical_outcomes=_rows(60, True, 1.5) + _rows(60, False, 1.0),
        realized_rr=1.5,
        cost_r=0.02,
    )
    assert result["trusted"] is True
    assert result["conditioning_mode"] == "EXACT_OR_PROGRESSIVELY_RELAXED"
    assert "CONDITIONAL_SAMPLE_RELAXED" not in result["blockers"]
    assert result["sample"] == 120


def test_relaxed_sample_cannot_be_trusted_as_exact_edge():
    rows = _rows(60, True, 1.5) + _rows(60, False, 1.0)
    for row in rows:
        row["confirmation"] = "UNKNOWN"
    result = evaluate_profit_edge(
        symbol="XAUUSD",
        regime="TREND_DOWN",
        direction="SELL",
        setup="TREND_PULLBACK",
        location="PREMIUM",
        confirmation="CONFIRMED",
        historical_outcomes=rows,
        realized_rr=1.5,
        cost_r=0.02,
    )
    assert result["trusted"] is False
    assert "CONDITIONAL_SAMPLE_RELAXED" in result["blockers"]


def _engine(engine_id, output):
    return EngineResult(engine_id, engine_id, False, 0.0, output, tuple(output.get("reason_codes", [])))


def test_e9_does_not_convert_actor_into_market_control():
    upstream = {
        "E1": _engine("E1", {"pressure": "DOWN"}),
        "E2": _engine("E2", {"direction": "SELL"}),
        "E3": _engine("E3", {"structure_integrity": "VALID", "structure_direction": "SELL"}),
        "E4": _engine("E4", {"response_actor": "BUYERS", "auction_state": "PENDING"}),
        "E5": _engine("E5", {"repricing_state": "UNKNOWN"}),
        "E6": _engine("E6", {"direction": "SELL", "setup": "TREND_PULLBACK", "thesis_state": "HYPOTHESIS"}),
        "E7": _engine("E7", {"confirmation_state": "PENDING"}),
        "E8": _engine("E8", {"risk_state": "UNRESOLVED"}),
    }
    result = analyze_e9({}, upstream).output
    assert result["control_direction"] == "SELL"
    assert all(item["source"] != "E4_AUCTION_RESPONSE" or item["direction"] != "BUY" for item in result["control_evidence"])
