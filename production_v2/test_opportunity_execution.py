from .opportunity_execution import evaluate_execution_geometry
from .runtime_compatibility import install


def test_good_opportunity_is_actionable_inside_optimal_zone():
    result = evaluate_execution_geometry(
        direction="BUY", entry=2480.0, stop=2477.0, target=2487.0,
        current_price=2480.5, atr=2.0, bars_since_event=1, event_type="LIQUIDITY_SWEEP",
    )
    assert result["state"] == "ACTIONABLE"
    assert result["rr"] > 1.5


def test_valid_thesis_becomes_too_late_when_rr_collapses():
    result = evaluate_execution_geometry(
        direction="BUY", entry=2480.0, stop=2477.0, target=2487.0,
        current_price=2485.0, atr=2.0, bars_since_event=1, event_type="LIQUIDITY_SWEEP",
    )
    assert result["state"] == "TOO_LATE"
    assert result["thesis_status"] == "VALID_BUT_MISSED"


def test_opportunity_expires_using_event_specific_ttl():
    result = evaluate_execution_geometry(
        direction="BUY", entry=2480.0, stop=2477.0, target=2487.0,
        current_price=2480.0, atr=2.0, bars_since_event=4, event_type="LIQUIDITY_SWEEP",
    )
    assert result["state"] == "EXPIRED"
    assert result["ttl_bars"] == 3


def test_invalid_geometry_is_not_marked_as_missed():
    result = evaluate_execution_geometry(
        direction="BUY", entry=2480.0, stop=2482.0, target=2487.0,
        current_price=2480.0, atr=2.0, bars_since_event=0, event_type="TREND_PULLBACK",
    )
    assert result["state"] == "INVALID_GEOMETRY"
    assert result["thesis_status"] == "INVALID"


def test_legacy_lifecycle_helper_accepts_new_causal_anchor_call():
    class Module:
        _directional_lifecycle_current = staticmethod(lambda results, decision, gate_passed, candle: (results, decision, gate_passed, candle))

    install(Module)
    assert Module._directional_lifecycle_current(1, 2, 3, 4, {"event_id": "x"}) == (1, 2, 3, 4)


def test_nested_varargs_wrapper_still_falls_back_to_legacy_four_args():
    def legacy(results, decision, gate_passed, candle):
        return results, decision, gate_passed, candle

    def varargs_wrapper(*args, **kwargs):
        return legacy(*args, **kwargs)

    class Module:
        _directional_lifecycle_current = staticmethod(varargs_wrapper)

    install(Module)
    assert Module._directional_lifecycle_current(1, 2, 3, 4, {"event_id": "x"}) == (1, 2, 3, 4)
