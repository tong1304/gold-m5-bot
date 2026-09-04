from types import SimpleNamespace

from production_v2.service import _pipeline_trace_fields


def test_trace_uses_public_decision_state_not_risk_engine_state():
    result = SimpleNamespace(
        decision="NO_TRADE",
        state="WAITING_FOR_CONFIRMATION",
        wait_bars=2,
        gate_passed=False,
        blocked_by=None,
        risk={"engine_state": None, "blocked_by": None},
        engines=(),
    )

    fields = _pipeline_trace_fields(result)

    assert fields == {
        "state": "WAITING_FOR_CONFIRMATION",
        "blocked_by": None,
        "wait_bars": 2,
    }
