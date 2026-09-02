import os

os.environ["PRODUCTION_V2_DISABLE_LIVE"] = "1"

from production_v2.app import _pending_upstream_thesis



def test_pending_upstream_thesis_accepts_contested_opportunity_watch():
    engines = {
        "E1": {
            "finding": "MARKET_STATE=TRANSITION; STRUCTURE=BULLISH; PRESSURE=DOWN",
            "direction": "UP",
        },
        "E2": {
            "direction": "NEUTRAL",
            "finding": "NEUTRAL opportunity is unproven based on closed-candle evidence.",
            "reasons": ["AUCTION_ACCEPTANCE_NOT_PROVEN", "DIRECTIONAL_EDGE_NOT_ESTABLISHED"],
        },
        "E3": {
            "finding": "BULLISH_STRUCTURE",
            "external_state": "UP",
            "internal_state": "DOWN",
        },
        "E4": {
            "finding": "LOW_ACCEPTANCE_CANDIDATE",
            "event": "LOW_ACCEPTANCE_CANDIDATE",
            "auction_state": "PENDING",
            "direction": "DOWN",
            "liquidity_taker": "SELLERS",
        },
        "E5": {
            "finding": "ACCEPTED_AUCTION_NO_REVERSAL_EDGE",
            "available_space_atr_long": 1.97,
            "available_space_atr_short": 0.47,
        },
        "E6": {
            "finding": "SELL AUCTION_ACCEPTANCE_CONTINUATION is forming",
            "setup": "AUCTION_ACCEPTANCE_CONTINUATION",
            "direction": "SELL",
            "reasons": ["E2_OPPORTUNITY_UNRESOLVED", "STRUCTURAL_SPACE_INSUFFICIENT"],
        },
    }

    direction, setup, evidence, wait_for = _pending_upstream_thesis(engines)

    assert direction == "BUY"
    assert setup == "OPPORTUNITY_WATCH"
    assert "OPPORTUNITY_SCOUTING_ACTIVE" in evidence
    assert "E4_DIRECTIONAL_RESOLUTION" in wait_for
