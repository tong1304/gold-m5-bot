from production_v2 import e9_brain


def test_e9_market_control_synthesizes_cross_engine_pressure_without_inventing_trap():
    e1 = {"finding": "MARKET_STATE=TRANSITION; PRESSURE=DOWN; STRUCTURE=BEARISH"}
    e2 = {"finding": "TRANSITION / BEARISH", "reason_codes": ["OPPORTUNITY_MATURITY"]}
    e3 = {"finding": "STRUCTURE_TRANSITION", "direction": "SELL"}
    e4 = {
        "finding": "LOW_LIQUIDITY_INTERACTION",
        "event": "LOW_LIQUIDITY_INTERACTION",
        "liquidity_taker": "SELLERS",
        "response_actor": "UNCLEAR",
        "event_level": 78117.95,
        "liquidity_type": "EQUAL_LIQUIDITY",
    }
    e5 = {
        "finding": "FAVORABLE_LOCATION",
        "value_state": "DISCOUNT",
        "available_space_atr_short": 1.2,
    }
    e6 = {"finding": "LIQUIDITY_REVERSAL", "direction": "SELL", "setup": "LIQUIDITY_REVERSAL", "maturity": "VALIDATING"}
    e7 = {"finding": "DEVELOPING", "direction": "SELL"}
    e8 = {"finding": "UNRESOLVED", "direction": "SELL"}

    result = e9_brain._market_control_brain(
        e1, e2, e3, e4, e5, e6, e7, e8, "SELL", "LIQUIDITY_REVERSAL", "SELL-side hypothesis"
    )

    assert result["dominant_actor"] == "SELLERS"
    assert result["controlled_side"] == "SELL"
    assert result["trapped_side"] == "NONE"
    assert result["market_intent"] in {"POTENTIAL_REPRICING_SELL", "DIRECTIONAL_INTENT_UNRESOLVED_DURING_TRANSITION"}
    assert result["state"] in {"CONTROL_FORMING", "CONTROL_UNPROVEN"}
