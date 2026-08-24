from v11.strategy_engine import _candidate_directions


def test_transition_with_neutral_h1_evaluates_both_m5_trigger_directions():
    context = {"regime": "TRANSITION", "direction": "SELL", "h1_bias": "NEUTRAL"}
    assert _candidate_directions(context) == ["BUY", "SELL"]


def test_transition_with_h1_bias_overrides_m5_side_and_evaluates_only_aligned_direction():
    context = {"regime": "TRANSITION", "direction": "SELL", "h1_bias": "BUY"}
    assert _candidate_directions(context) == ["BUY"]
