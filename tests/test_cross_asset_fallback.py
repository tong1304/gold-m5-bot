from v11.cross_asset_fallback import native_strategy_ids


def test_gold_native_strategies_never_include_btc_engines():
    for regime in ("TREND", "EXPANSION", "BREAKOUT_RETEST", "RANGE", "TRANSITION"):
        ids = native_strategy_ids("GOLD", regime)
        assert all(engine.startswith("G") for engine in ids)
        assert not set(ids) & {"B1", "B2", "B3"}


def test_btc_native_strategies_never_include_gold_engines():
    for regime in ("TREND", "EXPANSION", "BREAKOUT_RETEST", "RANGE", "TRANSITION"):
        ids = native_strategy_ids("BTC", regime)
        assert all(engine.startswith("B") for engine in ids)
        assert not set(ids) & {"G1", "G2", "G3"}


def test_known_regimes_keep_expected_native_families():
    assert native_strategy_ids("GOLD", "EXPANSION") == ["G2", "G3"]
    assert native_strategy_ids("BTC", "EXPANSION") == ["B1", "B2"]
