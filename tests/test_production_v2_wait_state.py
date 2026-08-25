from production_v2.pipeline import resolve_engine_state, WAIT_MAX_BARS


def test_unclear_evidence_waits_instead_of_passing_or_failing():
    state = resolve_engine_state(False, ("E7_CONFIRMATION_INSUFFICIENT",))
    assert state == "WAIT"


def test_invalidated_evidence_is_a_hard_fail():
    state = resolve_engine_state(False, ("E7_CONFIRMATION_INVALIDATED",))
    assert state == "FAIL"


def test_wait_state_expires_after_three_closed_m5_candles():
    assert WAIT_MAX_BARS == 3
    state = resolve_engine_state(False, ("E2_DIRECTION_UNCLEAR",), wait_bars=3)
    assert state == "FAIL"


def test_pass_remains_pass_regardless_of_score():
    assert resolve_engine_state(True, (), score=20.0) == "PASS"
    assert resolve_engine_state(True, (), score=95.0) == "PASS"
