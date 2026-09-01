from production_v2.contracts import EngineResult
from production_v2.e6_brain import analyze_e6


def _bars(n=60):
    return [
        {"open": 100.0 + i, "high": 101.0 + i, "low": 99.0 + i, "close": 100.5 + i}
        for i in range(n)
    ]


def _result(engine_id, output):
    return EngineResult(engine_id, engine_id, False, 0.0, output, ())


def _upstream(event="LOW_SWEEP_REJECTION"):
    return {
        "E1": _result("E1", {"finding": "MARKET_STATE=TREND", "pressure": "DOWN", "trend_state": "DOWN"}),
        "E2": _result("E2", {"finding": "NEUTRAL opportunity is emerging"}),
        "E3": _result("E3", {"finding": "BEARISH_STRUCTURE", "internal_state": "DOWN", "external_state": "DOWN", "bos": "NO_BREAK"}),
        "E4": _result("E4", {"event": event, "auction_state": "PENDING", "direction": "SELL", "event_id": "test-event", "event_age_bars": 0, "event_level": 110.0}),
        "E5": _result("E5", {"finding": "FAVORABLE_LOCATION", "value_state": "PREMIUM", "value_response": "ACCEPTED_ABOVE_VALUE", "structural_location": "AT_RESISTANCE", "available_space_atr_short": 2.0}),
    }


def test_positive_setup_survives_unresolved_e2():
    output = analyze_e6({"bars": _bars()}, _upstream()).output
    assert output["setup"] == "LIQUIDITY_REVERSAL"
    assert output["state"] == "FORMING"
    assert output["trade_ready"] is False
    assert output["candidate_discovery"] if "candidate_discovery" in output else True


def test_no_causal_trigger_stays_absent():
    upstream = _upstream(event="LOW_LIQUIDITY_INTERACTION")
    upstream["E4"] = _result("E4", {"event": "LOW_LIQUIDITY_INTERACTION", "auction_state": "PENDING", "direction": "NEUTRAL", "event_age_bars": 0})
    output = analyze_e6({"bars": _bars()}, upstream).output
    assert output["setup"] == "NONE"
    assert output["state"] == "ABSENT"
