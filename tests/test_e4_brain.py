import importlib


def _module():
    return importlib.import_module("production_v2.e4_brain")


def _bars(n=60, base=100.0):
    return [
        {"open": base, "high": base + 1.0, "low": base - 1.0, "close": base + 0.2}
        for _ in range(n)
    ]


def test_e4_does_not_use_future_pivot_information_for_liquidity_event():
    mod = _module()
    bars = _bars()
    # A level that only becomes a pivot because of candles AFTER the event
    # must not be available to classify the event at that earlier candle.
    bars[50] = {"open": 100.0, "high": 105.0, "low": 99.0, "close": 100.5}
    bars[51] = {"open": 100.5, "high": 101.0, "low": 99.5, "close": 100.0}
    bars[52] = {"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.2}
    bars[53] = {"open": 100.2, "high": 101.0, "low": 99.5, "close": 100.1}
    bars[54] = {"open": 100.1, "high": 101.0, "low": 99.5, "close": 100.0}
    result = mod.analyze_e4(bars)
    event = result["event"]
    assert event["index"] >= 55 or event["type"] == "NO_CONFIRMED_LIQUIDITY_EVENT"


def test_e4_never_promotes_current_candle_wick_to_confirmed_auction():
    mod = _module()
    bars = _bars()
    # Force a current-candle interaction shape; there are no subsequent
    # closed candles available to prove acceptance/rejection.
    bars[-1] = {"open": 100.0, "high": 104.0, "low": 99.8, "close": 100.2}
    result = mod.analyze_e4(bars)
    assert result["auction"]["confirmed"] is False
    assert result["auction_state"] in {
        "UNRESOLVED", "ACCEPTANCE_PENDING", "REJECTION_PENDING"
    }
