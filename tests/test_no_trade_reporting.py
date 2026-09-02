from types import SimpleNamespace

from production_v2.notifications.no_trade import _engine_compact
from production_v2.opportunity_lifecycle import advance_opportunity


def _engine(engine_id, output):
    return SimpleNamespace(engine_id=engine_id, output=output, reason_codes=(), gate_passed=False)


def test_e6_without_setup_reports_no_causal_setup_instead_of_none_is_absent():
    engine = _engine(
        "E6",
        {
            "direction": "BUY",
            "setup": "NONE",
            "setup_state": "NONE",
            "finding": "No causal setup hypothesis survives current closed-candle evidence.",
        },
    )
    text = _engine_compact(engine, "E6")
    assert text == "E6: No causal setup hypothesis survives current closed-candle evidence."
    assert "NONE is absent" not in text


def test_e2_wait_reports_watch_state_without_claiming_executable_setup():
    engine = _engine(
        "E2",
        {
            "opportunity_decision": "WAIT",
            "opportunity_direction": "BUY",
            "finding": "BUY WAIT",
        },
    )
    text = _engine_compact(engine, "E2")
    assert text == "E2: BUY WAIT"


def test_pending_watch_downgrade_is_not_reported_as_promotion_when_e6_disappears():
    previous = advance_opportunity(
        {},
        {
            "candidate": True,
            "direction": "BUY",
            "setup": "SWEEP_RECLAIM",
            "ready": False,
            "invalidated": False,
            "executed": False,
            "thesis_status": "FORMING",
            "candle": "2026-09-02T10:15:00Z",
        },
    )
    current = advance_opportunity(
        previous,
        {
            "candidate": True,
            "direction": "BUY",
            "setup": "OPPORTUNITY_WATCH",
            "ready": False,
            "invalidated": False,
            "executed": False,
            "thesis_status": "FORMING",
            "candle": "2026-09-02T10:20:00Z",
        },
    )
    assert current["state"] == "WAITING"
    assert current["continuity"] == "DOWNGRADED_TO_UPSTREAM_WATCH"
    assert current["setup"] == "OPPORTUNITY_WATCH"
    assert current["bars_waited"] == 1
