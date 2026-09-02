import os

os.environ.setdefault("PRODUCTION_V2_DISABLE_LIVE", "1")

from production_v2.app import _pending_upstream_thesis


def test_e2_developing_with_no_eligible_path_does_not_create_watch_without_independent_pending_event():
    direction, setup, evidence = _pending_upstream_thesis(
        {
            "E2": {
                "direction": "BUY",
                "finding": "UP opportunity is developing based on closed-candle evidence.",
                "opportunity_maturity": "DEVELOPING",
                "reasons": "NO_ELIGIBLE_OPPORTUNITY_PATH LOCATION_NOT_ADVANTAGEOUS INSUFFICIENT_OPPOSING_SPACE",
            },
            "E4": {
                "direction": "BUY",
                "auction_state": "CONFIRMED",
                "finding": "NO_ACTIVE_AUCTION",
                "reasons": "NONE",
            },
        }
    )
    assert direction == "BUY"
    assert setup == ""
    assert evidence == []


def test_pending_auction_can_keep_watch_alive_even_when_e2_path_is_not_yet_eligible():
    direction, setup, evidence = _pending_upstream_thesis(
        {
            "E2": {
                "direction": "BUY",
                "finding": "UP opportunity is developing based on closed-candle evidence.",
                "opportunity_maturity": "DEVELOPING",
                "reasons": "NO_ELIGIBLE_OPPORTUNITY_PATH LOCATION_NOT_ADVANTAGEOUS",
            },
            "E4": {
                "direction": "BUY",
                "auction_state": "PENDING",
                "finding": "HIGH_SWEEP_REJECTION",
                "reasons": "AUCTION_NOT_TERMINALLY_CONFIRMED TRUE_AUCTION_CONFIRMATION_NOT_PROVEN",
            },
        }
    )
    assert direction == "BUY"
    assert setup == "OPPORTUNITY_WATCH"
    assert "E4_AUCTION_PENDING" in evidence
    assert "E2_OPPORTUNITY_DEVELOPING" not in evidence
