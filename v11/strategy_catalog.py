STRATEGY_CATALOG = {
    "BTC": {
        "TREND_PULLBACK": {"lookback_m5": 60, "conditions": "EMA20/EMA50 alignment; EMA20 pullback within 12 M5 candles"},
        "BREAKOUT_RETEST": {"lookback_m5": 60, "conditions": "20-bar breakout; directional breakout candle; retest of breakout level"},
        "RANGE_BREAKOUT": {"lookback_m5": 31, "conditions": "20-bar range break; directional candle; body ratio >= 0.30"},
        "MOMENTUM": {"lookback_m5": 25, "conditions": "5-bar momentum move exceeds ATR14; directional candle; body ratio >= 0.45"},
        "VOLATILITY_BREAKOUT": {"lookback_m5": 50, "conditions": "ATR14 >= 1.25x median ATR30; 20-bar breakout; directional candle"},
    },
    "GOLD": {
        "TREND_PULLBACK": {"lookback_m5": 60, "conditions": "EMA20/EMA50 alignment; EMA20 pullback within 12 M5 candles"},
        "BREAKOUT_RETEST": {"lookback_m5": 60, "conditions": "20-bar breakout; directional breakout candle; retest of breakout level"},
        "EMA_PULLBACK": {"lookback_m5": 30, "conditions": "Previous M5 candle touches EMA20; current candle confirms close beyond EMA20"},
        "LIQUIDITY_SWEEP": {"lookback_m5": 35, "conditions": "Sweep prior 12-bar high/low; rejection close back inside range"},
        "SR_REVERSAL": {"lookback_m5": 45, "conditions": "20-bar support/resistance rejection; wick >= 1.2x body"},
        "VOLATILITY_BREAKOUT": {"lookback_m5": 50, "conditions": "ATR14 >= 1.25x median ATR30; 20-bar breakout; directional candle; body ratio >= 0.30"},
    },
}
