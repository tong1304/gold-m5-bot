from production_v2.e9_calibration import aggregate_samples


def test_small_sample_is_not_actionable():
    samples = [{"asset": "GOLD", "outcome": "WIN", "realized_r": 2.0} for _ in range(3)]
    stats = aggregate_samples(samples, min_samples=30)
    assert stats.sample_count == 3
    assert stats.actionable is False


def test_expectancy_is_average_realized_r():
    samples = [
        {"asset": "BTC", "outcome": "WIN", "realized_r": 2.0},
        {"asset": "BTC", "outcome": "LOSS", "realized_r": -1.0},
    ]
    stats = aggregate_samples(samples, min_samples=2)
    assert stats.expectancy_r == 0.5
    assert stats.win_rate == 0.5


def test_asset_filter_keeps_assets_isolated():
    samples = [
        {"asset": "GOLD", "outcome": "WIN", "realized_r": 2.0},
        {"asset": "BTC", "outcome": "LOSS", "realized_r": -1.0},
    ]
    stats = aggregate_samples(samples, min_samples=1, asset="GOLD")
    assert stats.sample_count == 1
    assert stats.expectancy_r == 2.0
