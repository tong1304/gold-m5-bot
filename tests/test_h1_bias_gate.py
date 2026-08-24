from v11.h1_gate import allows_trend_direction


def test_h1_buy_blocks_trend_sell_but_allows_buy():
    assert allows_trend_direction("BUY", "BUY") is True
    assert allows_trend_direction("BUY", "SELL") is False


def test_h1_sell_blocks_trend_buy_but_allows_sell():
    assert allows_trend_direction("SELL", "SELL") is True
    assert allows_trend_direction("SELL", "BUY") is False


def test_h1_neutral_does_not_force_trend_direction():
    assert allows_trend_direction("NEUTRAL", "BUY") is True
    assert allows_trend_direction("NEUTRAL", "SELL") is True
