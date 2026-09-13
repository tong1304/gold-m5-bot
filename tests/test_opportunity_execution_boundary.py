from production_v2.contracts import DecisionResult, EngineResult
from production_v2.opportunity_execution_boundary import apply_opportunity_execution_boundary


def _result(intelligence, *, decision="NO_TRADE", state="ANALYSIS_COMPLETE_NO_TRADE"):
    e9 = EngineResult(
        "E9",
        "Master Decision Brain",
        False,
        70.0,
        {"decision": decision},
        (),
    )
    return DecisionResult(
        symbol="BTC/USD",
        timeframe="M5",
        decision=decision,
        gate_passed=False,
        score=70.0,
        engines=(e9,),
        risk={"opportunity_intelligence": intelligence},
        reason_codes=(),
        state=state,
        blocked_by=None,
        wait_bars=0,
    )


def test_actionable_opportunity_becomes_prepare_without_authorizing_trade():
    intelligence = {
        "leader_stage": "HIGH_OPPORTUNITY",
        "leader_direction": "SELL",
        "leader_score": 86.0,
        "leader_entry_style": "CONFIRMED",
        "opportunity_id": "SELL|LIQUIDITY_RESPONSE|event-1",
    }
    result = apply_opportunity_execution_boundary(_result(intelligence))

    assert result.decision == "NO_TRADE"
    assert result.gate_passed is False
    assert result.state == "OPPORTUNITY_ACTIONABLE"
    assert result.risk["opportunity_action"] == "PREPARE"
    assert result.risk["opportunity_direction"] == "SELL"
    assert result.risk["trade_authorized"] is False


def test_watch_opportunity_does_not_become_prepare():
    intelligence = {
        "leader_stage": "WATCH",
        "leader_direction": "SELL",
        "leader_score": 62.0,
        "leader_entry_style": "WAIT",
        "opportunity_id": "SELL|LIQUIDITY_RESPONSE|event-2",
    }
    result = apply_opportunity_execution_boundary(_result(intelligence))

    assert result.decision == "NO_TRADE"
    assert result.state == "ANALYSIS_COMPLETE_NO_TRADE"
    assert result.risk["opportunity_action"] == "WATCH"
    assert result.risk["trade_authorized"] is False
