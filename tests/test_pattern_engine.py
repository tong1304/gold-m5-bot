from pattern_engine import confluence


def test_three_confirmed_same_direction_patterns_are_directional_confluence():
    patterns = [
        {"name": "Pattern A", "category": "PRICE_ACTION", "direction": "SELL", "confirmed": True},
        {"name": "Pattern B", "category": "PRICE_ACTION", "direction": "SELL", "confirmed": True},
        {"name": "Pattern C", "category": "PRICE_ACTION", "direction": "SELL", "confirmed": True},
    ]

    result = confluence(patterns, minimum=3)

    assert result["signal"] == "SELL"
    assert result["sell_evidence"] == patterns


def test_direction_with_three_patterns_can_beat_two_opposite_patterns():
    patterns = [
        {"name": "Sell A", "category": "PRICE_ACTION", "direction": "SELL", "confirmed": True},
        {"name": "Sell B", "category": "PRICE_ACTION", "direction": "SELL", "confirmed": True},
        {"name": "Sell C", "category": "PRICE_ACTION", "direction": "SELL", "confirmed": True},
        {"name": "Buy A", "category": "PRICE_ACTION", "direction": "BUY", "confirmed": True},
        {"name": "Buy B", "category": "PRICE_ACTION", "direction": "BUY", "confirmed": True},
    ]

    result = confluence(patterns, minimum=3)

    assert result["signal"] == "SELL"
