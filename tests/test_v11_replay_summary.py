from v11.replay import summarize_rows


def test_summarize_rows_reports_backtest_performance_and_strategy_breakdown():
    rows = [
        {"signal": "BUY", "strategy": "S1", "result": "WIN", "r_multiple": 2.0},
        {"signal": "SELL", "strategy": "S1", "result": "LOSS", "r_multiple": -1.0},
        {"signal": "BUY", "strategy": "S2", "result": "WIN", "r_multiple": 2.0},
        {"signal": "NO_TRADE", "strategy": "NONE", "result": "NO_TRADE", "r_multiple": 0.0},
    ]

    summary = summarize_rows(rows)

    assert summary["trades"] == 3
    assert summary["decided"] == 3
    assert summary["wins"] == 2
    assert summary["losses"] == 1
    assert summary["win_rate"] == 66.67
    assert summary["net_r"] == 3.0
    assert summary["expectancy_r"] == 1.0
    assert summary["profit_factor"] == 4.0
    assert summary["max_drawdown_r"] == 1.0
    assert summary["strategies"]["S1"]["trades"] == 2
    assert summary["strategies"]["S1"]["net_r"] == 1.0
    assert summary["strategies"]["S2"]["win_rate"] == 100.0


def test_summarize_rows_keeps_open_and_ambiguous_out_of_win_rate():
    rows = [
        {"signal": "BUY", "strategy": "S1", "result": "OPEN", "r_multiple": 0.0},
        {"signal": "SELL", "strategy": "S1", "result": "AMBIGUOUS", "r_multiple": 0.0},
        {"signal": "BUY", "strategy": "S1", "result": "LOSS", "r_multiple": -1.0},
    ]

    summary = summarize_rows(rows)

    assert summary["trades"] == 3
    assert summary["decided"] == 1
    assert summary["win_rate"] == 0.0
    assert summary["open"] == 1
    assert summary["ambiguous"] == 1
    assert summary["net_r"] == -1.0
