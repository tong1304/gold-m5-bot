from live_scanner import _resolve_m5_direction


def test_three_confirmed_sell_patterns_resolve_no_trade_confluence_to_sell():
    conf = {"signal": "NO_TRADE", "score": 42}
    buy_confirmed = []
    sell_confirmed = [
        {"name": "A", "direction": "SELL", "confirmed": True},
        {"name": "B", "direction": "SELL", "confirmed": True},
        {"name": "C", "direction": "SELL", "confirmed": True},
    ]

    assert _resolve_m5_direction(conf, buy_confirmed, sell_confirmed, minimum=3) == "SELL"


def test_two_confirmed_patterns_are_not_enough_to_resolve_no_trade():
    conf = {"signal": "NO_TRADE", "score": 24}
    sell_confirmed = [
        {"name": "A", "direction": "SELL", "confirmed": True},
        {"name": "B", "direction": "SELL", "confirmed": True},
    ]

    assert _resolve_m5_direction(conf, [], sell_confirmed, minimum=3) == "NO_TRADE"


def test_existing_confluence_direction_is_preserved():
    conf = {"signal": "BUY", "score": 60}
    buy_confirmed = [
        {"name": "A", "direction": "BUY", "confirmed": True},
        {"name": "B", "direction": "BUY", "confirmed": True},
        {"name": "C", "direction": "BUY", "confirmed": True},
    ]

    assert _resolve_m5_direction(conf, buy_confirmed, [], minimum=3) == "BUY"
