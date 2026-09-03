from production_v2.e6_opportunity_guard import _direction


def test_direction_accepts_multiple_candidate_fields():
    assert _direction("NEUTRAL", "SELL") == "SELL"
    assert _direction("NEUTRAL", "NEUTRAL", "BUY") == "BUY"


def test_direction_preserves_first_recognized_direction():
    assert _direction("SELL", "BUY") == "SELL"
    assert _direction("NEUTRAL", None, "SELLERS") == "SELL"
