from production_v2 import e2_opportunity_patch as patch


def test_setup_guard_accepts_explicit_pullback_phase():
    out = {
        "opportunity": "TREND_PULLBACK_CONTINUATION",
        "phase": "PULLBACK",
        "pullback_up": True,
    }
    assert patch._has_real_setup(out) is True


def test_setup_guard_rejects_trend_context_without_setup():
    out = {
        "opportunity": "TREND_PULLBACK_CONTINUATION",
        "phase": "DEVELOPING",
        "pullback_up": False,
        "pullback_down": False,
        "accepted_up": False,
        "accepted_down": False,
        "displacement_up": False,
        "displacement_down": False,
    }
    assert patch._has_real_setup(out) is False
