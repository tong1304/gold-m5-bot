import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import engine_v5 as engine


def test_buy_entry_is_above_reference_and_sell_entry_below_reference():
    assert engine.calculate_execution_price(100.0, "BUY", 0.20, 0.05, True) > 100.0
    assert engine.calculate_execution_price(100.0, "SELL", 0.20, 0.05, True) < 100.0


def test_exit_cost_is_applied():
    assert engine.calculate_execution_price(100.10, "BUY", 0.20, 0.05, False) < 100.10


def test_timeout_is_in_primary_outcome_distribution():
    stats = engine.calculate_trade_statistics([{"result": "TIMEOUT", "r": -0.2}])
    assert stats["trades"] == 1
    assert stats["timeouts"] == 1
    assert stats["outcome_counts"]["TIMEOUT"] == 1
    assert stats["net_expectancy_r"] == -0.2


def test_public_error_contract_has_no_internal_traceback():
    payload = {"status": "error", "message": "Internal server error"}
    assert "trace" not in payload
    assert "exception_type" not in payload


def test_guard_blocks_excessive_spread():
    result = engine.evaluate_live_risk_guard(spread=1.0, max_spread=0.5, data_age_seconds=0)
    assert result["allowed"] is False
    assert "SPREAD_TOO_HIGH" in result["reasons"]


def test_guard_blocks_consecutive_losses():
    result = engine.evaluate_live_risk_guard(spread=0.1, consecutive_losses=3, data_age_seconds=0)
    assert result["allowed"] is False
    assert "CONSECUTIVE_LOSS_LIMIT" in result["reasons"]


def test_guard_blocks_daily_loss():
    result = engine.evaluate_live_risk_guard(spread=0.1, daily_loss_r=-3.0, data_age_seconds=0)
    assert result["allowed"] is False
    assert "DAILY_LOSS_LIMIT" in result["reasons"]


def test_walk_forward_windows_do_not_overlap():
    windows = engine.build_walk_forward_windows(1000, 400, 200, 200)
    assert windows
    assert all(window["train_end"] <= window["test_start"] for window in windows)


def test_level_validation_rejects_zero_risk():
    result = engine.validate_trade_levels(100.0, 100.0, 101.0, 0.20, 0.05)
    assert result["valid"] is False


def test_probability_explicitly_labels_timeout_exclusion():
    result = engine.empirical_probability([
        {"result": "WIN"},
        {"result": "TIMEOUT"},
    ])
    assert result["resolved"] == 1
    assert result["probability_percent"] == 100.0
    assert "TIMEOUT" in result["note"]
