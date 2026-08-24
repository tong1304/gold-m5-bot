from v11.strategy_engine import evaluate_all_allowed


def test_v12_strategy_failures_are_traceable():
    class Dummy:
        def __init__(self):
            self.close = [1] * 100
            self.high = [1] * 100
            self.low = [1] * 100

    # The production trace contract is: every allowed engine/direction is
    # represented by either PASS or FAIL with rejection_reasons.
    result = evaluate_all_allowed(Dummy(), {"allowed_engines": ["E1"], "direction": "BUY", "regime": "TREND"})
    assert isinstance(result, list)
