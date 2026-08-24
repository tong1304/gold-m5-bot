from v11.replay import summarize_rows


def test_replay_summary_keeps_strategy_identity_and_trade_accounting():
    payload = summarize_rows([
        {"strategy": "TREND_PULLBACK", "result": "WIN", "r_multiple": 2.0},
        {"strategy": "TREND_PULLBACK", "result": "LOSS", "r_multiple": -1.0},
        {"strategy": "VWAP_MEAN_REVERSION", "result": "NO_TRADE", "r_multiple": 0.0},
        {"strategy": "LIQUIDITY_SWEEP", "result": "OPEN", "r_multiple": 0.0},
    ])
    assert payload["trades"] == 3
    assert payload["wins"] == 1
    assert payload["losses"] == 1
    assert payload["open"] == 1
    assert payload["no_trade"] == 1
    assert payload["strategies"]["TREND_PULLBACK"]["trades"] == 2
    assert payload["strategies"]["VWAP_MEAN_REVERSION"]["trades"] == 0


def test_no_trade_is_never_counted_as_trade():
    payload = summarize_rows([
        {"strategy": "NONE", "result": "NO_TRADE", "r_multiple": 0.0},
        {"strategy": "NONE", "result": "NO_TRADE", "r_multiple": 0.0},
    ])
    assert payload["trades"] == 0
    assert payload["no_trade"] == 2
