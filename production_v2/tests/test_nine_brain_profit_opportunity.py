from production_v2.nine_brain_profit_opportunity import synthesize_profit_opportunity


def _engine(direction="BUY", **extra):
    data = {"direction": direction, "state": "READY"}
    data.update(extra)
    return data


def test_nine_brains_expose_profitable_path_without_bypassing_e8_or_e9():
    results = {
        "E1": _engine(market_state="TREND_UP"),
        "E2": _engine(opportunity_state="OPPORTUNITY_WAITING"),
        "E3": _engine(structure_lifecycle="ESTABLISHED"),
        "E4": _engine(auction_state="ACCEPTED"),
        "E5": _engine(available_space_atr_long=2.4),
        "E6": _engine(setup="TREND_PULLBACK_CONTINUATION"),
        "E7": _engine(confirmation_state="CONFIRMED"),
        "E8": _engine(
            trade_plan={"valid": True, "real_rr": 1.8},
            real_rr=1.8,
            target_realism=0.8,
            stop_quality=0.8,
        ),
        "E9": _engine(decision="BUY", gate_passed=True, execution="APPROVED"),
    }

    opportunity = synthesize_profit_opportunity(results)

    assert opportunity["direction"] == "BUY"
    assert opportunity["opportunity"] is True
    assert opportunity["execution_ready"] is True
    assert opportunity["edge_stage"] == "EXECUTABLE"
    assert "E8" in opportunity["evidence"]
    assert "E9" in opportunity["evidence"]


def test_nine_brains_can_see_opportunity_while_economic_gate_still_blocks_execution():
    results = {
        "E1": _engine(market_state="TREND_UP"),
        "E2": _engine(opportunity_state="OPPORTUNITY_WAITING"),
        "E3": _engine(structure_lifecycle="ESTABLISHED"),
        "E4": _engine(auction_state="ACCEPTED"),
        "E5": _engine(available_space_atr_long=2.0),
        "E6": _engine(setup="TREND_PULLBACK_CONTINUATION"),
        "E7": _engine(confirmation_state="CONFIRMED"),
        "E8": _engine(
            trade_plan={"valid": False},
            real_rr=0.9,
            target_realism=0.3,
            stop_quality=0.4,
            reasons=["REAL_RR_BELOW_MINIMUM"],
        ),
        "E9": _engine(decision="NO_TRADE", gate_passed=False, execution="BLOCKED"),
    }

    opportunity = synthesize_profit_opportunity(results)

    assert opportunity["direction"] == "BUY"
    assert opportunity["opportunity"] is True
    assert opportunity["execution_ready"] is False
    assert opportunity["edge_stage"] == "ECONOMICS_BLOCKED"
    assert "REAL_RR_BELOW_MINIMUM" in opportunity["blockers"]
