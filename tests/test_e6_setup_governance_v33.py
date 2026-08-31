from production_v2.contracts import EngineResult
from production_v2.e6_brain import analyze_e6


def _bars(n=200):
    bars=[]
    price=100.0
    for i in range(n):
        close=price + (0.2 if i % 2 == 0 else -0.05)
        bars.append({"open": price, "high": max(price, close)+1.0, "low": min(price, close)-1.0, "close": close})
        price=close
    return bars


def _engine(engine_id, output):
    return EngineResult(engine_id, engine_id, False, 50.0, output, tuple(output.get("reason_codes", ())))


def test_pending_auction_exposes_single_primary_blocker_and_next_event():
    upstream = {
        "E1": _engine("E1", {"finding": "MARKET_STATE=TRANSITION", "pressure": "BALANCED"}),
        "E2": _engine("E2", {"finding": "UP opportunity is developing", "opportunity_maturity": "EMERGING"}),
        "E3": _engine("E3", {"finding": "BULLISH_STRUCTURE", "internal_state": "UP", "external_state": "UP", "lifecycle": "ESTABLISHED"}),
        "E4": _engine("E4", {"event": "LOW_FAILED_BREAK_RECLAIM", "auction_state": "PENDING", "event_age_bars": 0, "event_level": 99.0, "response_actor": "BUYERS"}),
        "E5": _engine("E5", {"available_space_atr_long": 2.0, "available_space_atr_short": 0.5}),
    }
    result = analyze_e6({"bars": _bars()}, upstream)
    out = result.output

    assert out["trade_ready"] is False
    assert out["maturity"] == "FORMING"
    assert out["primary_blocker"] == "AUCTION_CONFIRMATION_PENDING"
    assert out["next_required_event"] == "TERMINAL_AUCTION_CONFIRMATION"
    assert "AUCTION_CONFIRMATION_PENDING" in out["secondary_blockers"] or "AUCTION_PENDING" in out["secondary_blockers"]
