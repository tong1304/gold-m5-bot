from production_v2.e4_brain import analyze_e4


def _bars(n=40, start=100.0):
    bars = []
    price = start
    for i in range(n):
        o = price
        c = price + (0.15 if i % 2 == 0 else -0.05)
        h = max(o, c) + 0.25
        l = min(o, c) - 0.25
        bars.append({"open": o, "high": h, "low": l, "close": c, "closed": True})
        price = c
    return bars


def test_e4_exposes_causal_auction_reasoning_contract():
    result = analyze_e4({"bars": _bars()})
    reasoning = result["professional_reasoning"]
    for key in ("liquidity_event", "take", "response", "acceptance", "rejection", "follow_through", "thesis_status", "counter_evidence", "invalidation"):
        assert key in reasoning


def test_e4_never_claims_actual_participants_from_ohlc():
    result = analyze_e4({"bars": _bars()})
    assert result["professional_reasoning"]["actor_identification"] == "OHLC_INFERENCE_ONLY"
    assert result["audit"]["actor_identification"] == "PRICE_ACTION_INFERENCE_ONLY"


def test_e4_pending_interaction_is_not_directional_confirmation():
    result = analyze_e4({"bars": _bars()})
    reasoning = result["professional_reasoning"]
    if reasoning["liquidity_event"]["state"] == "INTERACTION":
        assert reasoning["thesis_status"] == "UNRESOLVED"
        assert result["direction_confirmed"] is False
