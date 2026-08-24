STRATEGY_CATALOG={
    "BTC":{
        "TREND_PULLBACK":{"lookback_m5":"dynamic<=100","conditions":"M15 HH/HL or LH/LL trend; EMA20/50 direction filter; pullback into structural/EMA safe zone; confirmed candle break; structural SL; nearest opposing structure must allow >=2R"},
        "BREAKOUT_RETEST":{"lookback_m5":"dynamic<=100","conditions":"Repeated structural S/R level; close-confirmed breakout; retest of level; confirmed candle; structural SL; nearest opposing structure must allow >=2R"},
        "LIQUIDITY_SWEEP":{"lookback_m5":"dynamic<=100","conditions":"Latest confirmed swing liquidity; sweep beyond level and close back inside; next closed candle confirms reclaim; structural SL; opposing liquidity/structure must allow >=2R"},
        "VWAP_MOMENTUM_PULLBACK":{"lookback_m5":"dynamic<=100","conditions":"Session VWAP slope; momentum expansion; pullback to VWAP; confirmed candle continuation; structural SL; opposing structure must allow >=2R"},
        "OPENING_RANGE_BREAKOUT":{"lookback_m5":"dynamic<=100; range defined by time window","conditions":"Opening range from configurable time window; volatility-sized range; close-confirmed breakout/retest; structural SL; opposing structure must allow >=2R"},
    },
    "GOLD":{
        "TREND_PULLBACK":{"lookback_m5":"dynamic<=100","conditions":"M15 HH/HL or LH/LL trend; EMA20/50 direction filter; pullback into structural/EMA safe zone; confirmed candle break; structural SL; nearest opposing structure must allow >=2R"},
        "BREAKOUT_RETEST":{"lookback_m5":"dynamic<=100","conditions":"Repeated structural S/R level; close-confirmed breakout; retest of level; confirmed candle; structural SL; nearest opposing structure must allow >=2R"},
        "LIQUIDITY_SWEEP":{"lookback_m5":"dynamic<=100","conditions":"Latest confirmed swing liquidity; sweep beyond level and close back inside; next closed candle confirms reclaim; structural SL; opposing liquidity/structure must allow >=2R"},
        "VWAP_MOMENTUM_PULLBACK":{"lookback_m5":"dynamic<=100","conditions":"Session VWAP slope; momentum expansion; pullback to VWAP; confirmed candle continuation; structural SL; opposing structure must allow >=2R"},
        "OPENING_RANGE_BREAKOUT":{"lookback_m5":"dynamic<=100; range defined by time window","conditions":"Opening range from configurable time window; volatility-sized range; close-confirmed breakout/retest; structural SL; opposing structure must allow >=2R"},
    },
}
