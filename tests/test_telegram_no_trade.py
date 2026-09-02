from types import SimpleNamespace

from production_v2.notifications.no_trade import format_no_trade


def _engine(engine_id, output=None, reasons=()):
    return SimpleNamespace(engine_id=engine_id, output=output or {}, reason_codes=tuple(reasons))


def test_no_trade_reports_real_engine_states_and_e9_decision():
    result = SimpleNamespace(
        decision="NO_TRADE",
        gate_passed=False,
        reason_codes=("E8_RR_BELOW_MINIMUM",),
        risk={
            "opportunity_lifecycle": {
                "state": "WAITING",
                "continuity": "CONTINUING_EXISTING_OPPORTUNITY",
                "bars_waited": 2,
                "opportunity_id": "SELL|AUCTION_ACCEPTANCE_CONTINUATION",
                "next_required_event": "NEXT_CLOSED_M5_CANDLE",
            }
        },
        engines=[
            _engine("E1", {"market_state": "TREND_DOWN", "volatility_state": "EXPANDING", "structure_state": "BEARISH", "directional_pressure": "DOWN", "trend_state": "DOWN", "transition": "ABSENT"}),
            _engine("E2", {"opportunity_decision": "DEVELOPING", "opportunity_direction": "DOWN", "opportunity_state": "FORMING"}),
            _engine("E3", {"finding": "STRUCTURE_FORMING"}),
            _engine("E4", {"finding": "LOW_ACCEPTANCE_CANDIDATE", "auction_state": "PENDING"}),
            _engine("E5", {"value_position": "EQUILIBRIUM", "value_response": "REJECTED_BELOW_VALUE", "repricing_state": "REPRICING_FAILED"}),
            _engine("E6", {"direction": "SELL", "setup": "AUCTION_ACCEPTANCE_CONTINUATION", "setup_state": "FORMING"}),
            _engine("E7", {"confirmation_state": "HYPOTHESIS_ONLY", "is_confirmation": False}),
            _engine("E8", {"trade_plan": {"valid": False}, "real_rr": 0.9}),
            _engine("E9", {"decision": "NO_TRADE", "decision_reasons": ["E8_RR_BELOW_MINIMUM"]}),
        ],
    )

    text = format_no_trade({"BTC": result})

    assert "E1: MARKET_STATE=TREND_DOWN" in text
    assert "E2: DOWN opportunity is developing" in text or "E2: DEVELOPING" in text
    assert "E4: LOW_ACCEPTANCE_CANDIDATE" in text
    assert "E6: SELL AUCTION_ACCEPTANCE_CONTINUATION" in text
    assert "E9: NO_TRADE" in text
    assert "UNRESOLVED" not in text
    assert "OPPORTUNITY_LIFECYCLE: WAITING" in text
    assert "CONTINUING_EXISTING_OPPORTUNITY" in text
    assert "bars_waited=2" in text
    assert "NEXT_CLOSED_M5_CANDLE" in text
    assert "🔄 รอหลักฐานเพิ่มเติมเมื่อแท่ง M5 ปิดถัดไป" in text
