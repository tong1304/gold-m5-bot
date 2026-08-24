from v11.decision_priority import choose_priority_setup, signal_reason


def test_e7_always_beats_e4_and_e8_when_multiple_setups_pass():
    candidates = [
        {"engine": "E8", "strategy": "RANGE_REJECTION", "quality": 99},
        {"engine": "E4", "strategy": "BREAK_RETEST_CONTINUATION", "quality": 90},
        {"engine": "E7", "strategy": "SWEEP_REJECTION_REVERSAL", "quality": 70},
    ]
    assert choose_priority_setup(candidates)["engine"] == "E7"


def test_e4_beats_e8_when_e7_is_absent():
    candidates = [
        {"engine": "E8", "strategy": "RANGE_REJECTION", "quality": 99},
        {"engine": "E4", "strategy": "BREAK_RETEST_CONTINUATION", "quality": 70},
    ]
    assert choose_priority_setup(candidates)["engine"] == "E4"


def test_signal_reason_is_never_empty_for_signal():
    assert signal_reason({"signal": "BUY", "engine": "E8", "strategy": "RANGE_REJECTION"}) == "E8_RANGE_REJECTION_PASS"


def test_signal_reason_for_no_trade_uses_rejection_reason():
    assert signal_reason({"signal": "NO_TRADE", "rejection_reasons": ["NO_ALLOWED_ENGINE_SETUP"]}) == "NO_ALLOWED_ENGINE_SETUP"
