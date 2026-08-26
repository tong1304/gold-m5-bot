from types import SimpleNamespace

from production_v2.professional_brain import (
    _confirmation_state,
    _independent_setup_maturity,
    _structured_direction,
)


def engine(engine_id, output, score=70.0):
    return SimpleNamespace(
        engine_id=engine_id,
        name=engine_id,
        score=score,
        output=output,
        reason_codes=(),
    )


def test_trigger_observed_is_not_confirmation():
    e7 = engine("E7", {
        "state": "TRIGGER_OBSERVED",
        "direction": "SELL",
        "finding": "FOLLOW_THROUGH_OBSERVED;WAIT;CONFIRMATION_WAIT",
    })
    assert _confirmation_state(e7) == "WAIT"


def test_explicit_confirmation_is_confirmation():
    e7 = engine("E7", {
        "state": "TRIGGER_OBSERVED",
        "direction": "SELL",
        "confirmation_state": "CONFIRMED",
        "finding": "FOLLOW_THROUGH_OBSERVED;CONFIRMATION_PASS",
    })
    assert _confirmation_state(e7) == "CONFIRMED"


def test_setup_can_be_mature_before_confirmation():
    by = {
        "E3": engine("E3", {"direction": "SELL", "state": "STRUCTURE_BREAK"}),
        "E5": engine("E5", {"direction": "SELL", "state": "LOCATION_QUALITY_PASS"}),
        "E6": engine("E6", {"direction": "SELL", "state": "MATURE"}),
        "E7": engine("E7", {"direction": "SELL", "state": "TRIGGER_OBSERVED", "confirmation_state": "WAIT"}),
    }
    result = _independent_setup_maturity(by, "SELL")
    assert result["state"] == "MATURE"
    assert result["mature"] is True
    assert result["trigger"] is True
    assert result["confirmation"] is False


def test_direction_prefers_structured_direction_over_unresolved_placeholder():
    e = engine("E3", {
        "direction": "UNRESOLVED",
        "finding": "STRUCTURE_BREAK;DOWN;STRONG;ALIGNED",
    })
    assert _structured_direction(e) == "SELL"
