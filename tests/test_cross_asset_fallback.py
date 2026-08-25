from v11.cross_asset_fallback import cross_asset_strategy_ids, native_strategy_ids


def test_gold_falls_back_to_btc_strategies_for_shared_regime():
    assert cross_asset_strategy_ids("GOLD", "EXPANSION") == ["B1", "B2"]


def test_btc_falls_back_to_gold_strategies_for_shared_regime():
    assert cross_asset_strategy_ids("BTC", "EXPANSION") == ["G2", "G3"]


def test_no_cross_asset_strategy_means_no_fallback():
    assert cross_asset_strategy_ids("GOLD", "TREND") == []


def test_native_strategy_has_priority_over_cross_asset_fallback():
    assert native_strategy_ids("GOLD", "EXPANSION") == ["G2", "G3"]
    assert native_strategy_ids("BTC", "EXPANSION") == ["B1", "B2"]
