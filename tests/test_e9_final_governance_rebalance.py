from production_v2.e9_brain import analyze_e9
from production_v2.contracts import EngineResult


def engine(name, output=None, reasons=()):
    return EngineResult(name, name, False, 0.0, output or {}, tuple(reasons))


def base_upstream(e6=None, e7=None, e8=None, e2=None, e3=None):
    return {
        "E1": engine("E1", {"pressure": "UP"}),
        "E2": engine("E2", e2 or {"direction": "BUY"}),
        "E3": engine("E3", e3 or {"structure_integrity": "VALID", "structure_direction": "UP"}),
        "E4": engine("E4", {"auction_state": "PENDING", "response_actor": "UNCLEAR"}),
        "E5": engine("E5", {}),
        "E6": engine("E6", e6 or {}),
        "E7": engine("E7", e7 or {}),
        "E8": engine("E8", e8 or {}),
    }


def trade_ready_e6():
    return {
        "direction": "BUY",
        "setup": "AUCTION_ACCEPTANCE_CONTINUATION",
        "thesis": "Buy continuation after accepted auction and follow-through.",
        "thesis_state": "MATURE",
        "maturity": "MATURE",
    }


def trade_ready_e7():
    return {
        "confirmation_state": "PROVEN",
        "trigger_observed": True,
        "valid_trigger": True,
        "closed_candle_trigger": True,
    }


def trade_ready_e8():
    return {
        "economic_state": "READY",
        "verified": True,
        "entry": 100.0,
        "stop_loss": 99.0,
        "take_profit": 102.0,
        "rr": 2.0,
    }


def test_e9_executes_when_core_thesis_trigger_and_survivable_economics_pass_even_if_supporting_evidence_is_mixed():
    upstream = base_upstream(
        e6=trade_ready_e6(),
        e7=trade_ready_e7(),
        e8=trade_ready_e8(),
        e2={
            "direction": "BUY",
            "reason_codes": [
                "AUCTION_CONFIRMATION_PENDING",
                "LOCATION_NOT_ADVANTAGEOUS",
                "OPPOSING_SPACE_CONSTRAINED",
            ],
        },
    )

    result = analyze_e9({}, upstream)

    assert result.output["decision"] == "BUY"
    assert result.output["final_governance"] == "EXECUTE"
    assert result.output["execution_state"] == "APPROVED"
    assert result.output["all_gates_pass"] is True
    assert result.output["opportunity_state"] == "EXECUTE"
    assert result.output["opportunity"]["do_not_execute"] is False


def test_e9_watches_a_surviving_thesis_when_trigger_is_not_yet_proven():
    upstream = base_upstream(
        e6={
            "direction": "BUY",
            "setup": "AUCTION_ACCEPTANCE_CONTINUATION",
            "thesis": "Continuation thesis is forming.",
            "thesis_state": "VALIDATING",
            "maturity": "DEVELOPING",
        },
        e7={"confirmation_state": "PENDING"},
        e8={},
    )

    result = analyze_e9({}, upstream)

    assert result.output["decision"] == "NO_TRADE"
    assert result.output["final_governance"] == "WATCH"
    assert result.output["execution_state"] == "BLOCKED"
    assert result.output["opportunity_state"] == "WATCH"
    assert "E7_CONFIRMATION_REQUIRED" in result.output["next_required_events"]


def test_e9_no_trade_when_e6_has_no_surviving_thesis():
    result = analyze_e9({}, base_upstream(e6={"finding": "No causal setup hypothesis survives."}))

    assert result.output["decision"] == "NO_TRADE"
    assert result.output["final_governance"] == "NO_THESIS"
    assert result.output["opportunity_state"] == "NO_THESIS"
    assert result.output["all_gates_pass"] is False


def test_e9_no_trade_on_fatal_risk_even_when_thesis_and_trigger_are_proven():
    upstream = base_upstream(
        e6=trade_ready_e6(),
        e7=trade_ready_e7(),
        e8={
            **trade_ready_e8(),
            "economic_state": "BLOCKED",
            "economic_blockers": ["INVALID_TRADE_GEOMETRY"],
        },
    )

    result = analyze_e9({}, upstream)

    assert result.output["decision"] == "NO_TRADE"
    assert result.output["final_governance"] == "REJECTED_HARD_CONFLICT" or result.output["economic_state"] == "BLOCKED"
    assert result.output["execution_state"] == "BLOCKED"
    assert result.output["opportunity"]["do_not_execute"] is True
