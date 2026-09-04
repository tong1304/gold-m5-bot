from production_v2 import e8_applicability_boundary as e8_boundary
from production_v2 import e9_brain


def test_e8_accepts_concrete_setup_thesis_even_with_legacy_no_causal_diagnostic():
    e6 = {
        "setup": "LIQUIDITY_REVERSAL",
        "direction": "BUY",
        "state": "SETUP_THESIS",
        "thesis_status": "FORMING",
        "watch_only": False,
        "trade_ready": False,
        "reason_codes": ["NO_CAUSAL_OPPORTUNITY"],
    }
    assert e8_boundary._has_surviving_thesis(e6) is True


def test_e9_treats_setup_thesis_as_a_surviving_hypothesis():
    e6 = {
        "setup": "LIQUIDITY_REVERSAL",
        "direction": "BUY",
        "state": "SETUP_THESIS",
        "thesis_status": "FORMING",
    }
    assert e9_brain._thesis_state(e6) == "HYPOTHESIS"
    identity = e9_brain._e6_identity(e6)
    assert e9_brain._has_surviving_thesis(e6, identity) is True
