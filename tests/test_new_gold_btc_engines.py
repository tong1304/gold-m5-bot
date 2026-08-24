import pandas as pd


def _frame(n=80, base=100.0):
    rows=[]
    for i in range(n):
        o=base+i*0.1
        rows.append({"open":o,"high":o+1,"low":o-1,"close":o+0.5,"volume":1000+i})
    return pd.DataFrame(rows)


def test_new_gold_engine_set_has_exactly_three_engines():
    from v11.new_gold_engines import GOLD_NEW_ENGINE_NAMES
    assert list(GOLD_NEW_ENGINE_NAMES) == ["G1","G2","G3"]
    assert GOLD_NEW_ENGINE_NAMES["G1"] == "LIQUIDITY_SWEEP_CHOCH"
    assert GOLD_NEW_ENGINE_NAMES["G2"] == "CONTINUATION_FVG_PULLBACK"
    assert GOLD_NEW_ENGINE_NAMES["G3"] == "SESSION_BREAKOUT_RETEST"


def test_new_btc_engine_set_has_exactly_three_engines():
    from v11.new_btc_engines import BTC_NEW_ENGINE_NAMES
    assert list(BTC_NEW_ENGINE_NAMES) == ["B1","B2","B3"]
    assert BTC_NEW_ENGINE_NAMES["B1"] == "RANGE_SWEEP_DISPLACEMENT"
    assert BTC_NEW_ENGINE_NAMES["B2"] == "HTF_OB_M5_FVG_RETEST"
    assert BTC_NEW_ENGINE_NAMES["B3"] == "VOLATILITY_EXPANSION_BREAKOUT_RETEST"


def test_new_engine_maps_do_not_change_legacy_maps():
    from v11.gold_engines import GOLD_ENGINE_NAMES
    from v11.btc_engines import BTC_ENGINE_NAMES
    assert set(GOLD_ENGINE_NAMES) == {"G1","G2","G3","G4","G5"}
    assert set(BTC_ENGINE_NAMES) == {"B1","B2","B3"}


def test_btc_new_engines_keep_strict_rr_metadata_contract():
    from v11.new_btc_engines import BTC_NEW_ENGINE_MIN_RR
    assert BTC_NEW_ENGINE_MIN_RR["B1"] == 2.0
    assert BTC_NEW_ENGINE_MIN_RR["B2"] == 3.0
    assert BTC_NEW_ENGINE_MIN_RR["B3"] == 1.5
