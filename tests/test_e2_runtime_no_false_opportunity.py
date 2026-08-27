from production_v2.engines import run_engine


def _monotonic_down_snapshot(n=200):
    bars = []
    price = 3000.0
    for _ in range(n):
        close = price - 2.0
        bars.append({
            "open": price,
            "high": price + 0.25,
            "low": close - 0.25,
            "close": close,
        })
        price = close
    return {"bars": bars}


def test_e2_logical_thesis_matches_guarded_wait_state():
    result = run_engine("E2", _monotonic_down_snapshot(), {})
    output = result.output

    assert output["opportunity"] == "WAIT_FOR_REPRICING"
    assert output["phase"] == "TRANSITION"
    assert output["opportunity_state"] == "WAIT"
    assert output["opportunity_decision"] == "WAIT"
    assert output["opportunity_score"] == 0.0
    assert output["thesis"].startswith("Trend context detected")
