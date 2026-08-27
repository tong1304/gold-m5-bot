import importlib
import inspect


def test_e5_exposes_observable_location_evidence():
    mod = importlib.import_module("production_v2.e5_brain")
    source = inspect.getsource(mod)
    assert "observations" in source
    assert "value_distance_atr" in source
    assert "available_space_atr" in source
    assert "extension_atr" in source
    assert "counter_evidence" in source


def test_e5_remains_location_only():
    mod = importlib.import_module("production_v2.e5_brain")
    source = inspect.getsource(mod)
    assert "LOCATION" in source
    assert "BUY" not in source.upper().replace("BUYER", "")
    assert "SELL" not in source.upper().replace("SELLER", "")
