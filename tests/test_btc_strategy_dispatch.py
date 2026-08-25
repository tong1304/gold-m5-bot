import pandas as pd


def _frame(n=100, base=100.0):
    rows = []
    start = pd.Timestamp("2026-08-25T00:00:00Z")
    for i in range(n):
        o = base + i * 0.05
        rows.append({
            "datetime": start + pd.Timedelta(minutes=5 * i),
            "open": o,
            "high": o + 1.0,
            "low": o - 1.0,
            "close": o + 0.2,
            "volume": 1000 + i,
        })
    return pd.DataFrame(rows)


def test_btc_dispatch_always_evaluates_all_three_strategies_and_directions():
    from v11.btc_strategy_dispatch import evaluate_btc_strategies

    candidates, trace = evaluate_btc_strategies(_frame(), {
        "m5_regime": "TREND",
        "regime": "TREND",
        "h1_bias": "BUY",
        "m15_trend": "BUY",
    })

    assert len(trace) == 6
    assert {(item["engine"], item["direction"]) for item in trace} == {
        ("B1", "BUY"), ("B1", "SELL"),
        ("B2", "BUY"), ("B2", "SELL"),
        ("B3", "BUY"), ("B3", "SELL"),
    }
    assert all(item.get("status") in {"PASS", "FAIL"} for item in trace)
    assert all(item.get("engine") in {"B1", "B2", "B3"} for item in trace)
    assert all("score_detail" in item for item in trace)
    assert isinstance(candidates, list)
