from types import SimpleNamespace

from production_v2.mtf_runtime import _first_blocker


def _engine(engine_id, output):
    return SimpleNamespace(engine_id=engine_id, output=output)


def _result(*engines, decision="NO_TRADE", gate_passed=False):
    return SimpleNamespace(engines=engines, decision=decision, gate_passed=gate_passed)


def test_watch_is_blocked_first_by_e7_not_e8_or_e9():
    result = _result(
        _engine("E6", {"setup": "OPPORTUNITY_WATCH", "watch_only": True}),
        _engine("E7", {"confirmation": "NOT_APPLICABLE", "reason_codes": ["E6_THESIS_NOT_CONFIRMED"]}),
        _engine("E8", {"economic_state": "NOT_APPLICABLE", "reason_codes": ["E6_THESIS_REQUIRED"]}),
        _engine("E9", {"decision": "NO_TRADE"}),
    )
    assert _first_blocker(result) == ("E7", "E6_THESIS_NOT_CONFIRMED")


def test_confirmed_setup_with_bad_economics_is_blocked_by_e8():
    result = _result(
        _engine("E6", {"setup": "LIQUIDITY_REVERSAL", "setup_state": "MATURE"}),
        _engine("E7", {"confirmation": "CONFIRMED"}),
        _engine("E8", {"economic_state": "ECONOMICALLY_INVALID", "gate_passed": False, "reason_codes": ["REAL_RR_BELOW_MINIMUM"]}),
        _engine("E9", {"decision": "NO_TRADE"}),
    )
    assert _first_blocker(result) == ("E8", "REAL_RR_BELOW_MINIMUM")
