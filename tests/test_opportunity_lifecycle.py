from production_v2.app import _pending_upstream_thesis
from production_v2.opportunity_lifecycle import advance_opportunity


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


def test_upstream_watch_invalidates_when_causal_evidence_is_lost():
    first = advance_opportunity(
        {},
        {
            "candidate": True,
            "direction": "BUY",
            "setup": "OPPORTUNITY_WATCH",
            "upstream_evidence": ["E4_AUCTION_PENDING"],
            "ready": False,
            "invalidated": False,
            "executed": False,
            "thesis_status": "FORMING",
            "candle": "2026-09-02T10:10:00Z",
        },
    )
    lost = advance_opportunity(
        first,
        {
            "candidate": True,
            "direction": "BUY",
            "setup": "OPPORTUNITY_WATCH",
            "upstream_evidence": [],
            "ready": False,
            "invalidated": False,
            "executed": False,
            "thesis_status": "FORMING",
            "candle": "2026-09-02T10:15:00Z",
        },
    )
    assert lost["state"] == "INVALIDATED"
    assert lost["invalidation_reason"] == "UPSTREAM_CAUSAL_EVIDENCE_LOST"


def test_upstream_watch_reports_distinct_continuation():
    first = advance_opportunity(
        {},
        {
            "candidate": True,
            "direction": "BUY",
            "setup": "OPPORTUNITY_WATCH",
            "upstream_evidence": ["E4_AUCTION_PENDING"],
            "ready": False,
            "invalidated": False,
            "executed": False,
            "thesis_status": "FORMING",
            "candle": "2026-09-02T10:10:00Z",
        },
    )
    second = advance_opportunity(
        first,
        {
            "candidate": True,
            "direction": "BUY",
            "setup": "OPPORTUNITY_WATCH",
            "upstream_evidence": ["E4_AUCTION_PENDING", "E4_EVENT_PRESENT"],
            "ready": False,
            "invalidated": False,
            "executed": False,
            "thesis_status": "FORMING",
            "candle": "2026-09-02T10:15:00Z",
        },
    )
    assert second["state"] == "WAITING"
    assert second["continuity"] == "CONTINUING_UPSTREAM_WATCH"
    assert second["bars_waited"] == 1
