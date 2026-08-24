STRATEGY_CATALOG={
    "BTC":{
        "E1_TREND":{"regimes":["TREND"],"conditions":"EMA20>EMA50>EMA200 or inverse; structure HH/HL or LH/LL; ADX14>=25; DI direction; continuation trigger"},
        "E2_TREND_PULLBACK":{"regimes":["TREND"],"conditions":"Impulse >= ATR; pullback into EMA/structure zone; continuation candle trigger"},
        "E3_BREAKOUT":{"regimes":["TREND","TRANSITION"],"conditions":"Range high/low break; body expansion; volume ratio confirmation"},
        "E4_BREAKOUT_RETEST":{"regimes":["TREND","TRANSITION"],"conditions":"Confirmed break; retest of broken level; continuation trigger"},
        "E5_MOMENTUM":{"regimes":["TREND"],"conditions":"Strong candle; body>=0.70 ATR; volume ratio>=1.5; ATR expansion"},
        "E6_MEAN_REVERSION":{"regimes":["RANGE"],"conditions":"Extreme >=1.5 ATR from VWAP; rejection; return toward VWAP"},
        "E7_LIQUIDITY_REVERSAL":{"regimes":["RANGE","TRANSITION"],"conditions":"Sweep confirmed swing; rejection; reversal trigger"},
        "E8_RANGE":{"regimes":["RANGE"],"conditions":"Range high/low rejection with wick/body confirmation"},
    },
    "GOLD":{
        "E1_TREND":{"regimes":["TREND"],"conditions":"EMA20>EMA50>EMA200 or inverse; structure HH/HL or LH/LL; ADX14>=25; DI direction; continuation trigger"},
        "E2_TREND_PULLBACK":{"regimes":["TREND"],"conditions":"Impulse >= ATR; pullback into EMA/structure zone; continuation candle trigger"},
        "E3_BREAKOUT":{"regimes":["TREND","TRANSITION"],"conditions":"Range high/low break; body expansion; volume ratio confirmation"},
        "E4_BREAKOUT_RETEST":{"regimes":["TREND","TRANSITION"],"conditions":"Confirmed break; retest of broken level; continuation trigger"},
        "E5_MOMENTUM":{"regimes":["TREND"],"conditions":"Strong candle; body>=0.70 ATR; volume ratio>=1.5; ATR expansion"},
        "E6_MEAN_REVERSION":{"regimes":["RANGE"],"conditions":"Extreme >=1.5 ATR from VWAP; rejection; return toward VWAP"},
        "E7_LIQUIDITY_REVERSAL":{"regimes":["RANGE","TRANSITION"],"conditions":"Sweep confirmed swing; rejection; reversal trigger"},
        "E8_RANGE":{"regimes":["RANGE"],"conditions":"Range high/low rejection with wick/body confirmation"},
    },
}
