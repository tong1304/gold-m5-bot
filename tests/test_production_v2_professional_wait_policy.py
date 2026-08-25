from production_v2.pipeline import (
    WAIT_MAX_BARS,
    resolve_engine_state,
    resume_from_wait,
)


def test_wait_has_no_fixed_three_bar_expiry():
    assert WAIT_MAX_BARS is None
    assert resolve_engine_state(False, ("E2_DIRECTION_UNCLEAR",), wait_bars=20) == "WAIT"


def test_hard_risk_failure_is_immediate_fail():
    assert resolve_engine_state(False, ("E8_RR_BELOW_MINIMUM",)) == "FAIL"


def test_waiting_confirmation_resumes_only_from_waiting_engine_when_structure_is_unchanged():
    assert resume_from_wait("E7", structure_changed=False) == "E7"


def test_structure_change_reopens_pipeline_from_e3():
    assert resume_from_wait("E7", structure_changed=True) == "E3"


def test_waiting_e2_does_not_jump_past_the_waiting_engine():
    assert resume_from_wait("E2", structure_changed=False) == "E2"
