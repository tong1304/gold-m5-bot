from production_v2.contracts import EngineResult
from production_v2.professional_brain import _independent_setup_maturity


def _engine(engine_id, output, score=80.0):
    return EngineResult(engine_id, engine_id, None, score, output, ())


def test_e9_does_not_promote_forming_setup_to_mature():
    by = {
        "E3": _engine("E3", {"specialists": {"3F": {"output": {"state": "ALIGNED", "direction": "DOWN"}}}}),
        "E5": _engine("E5", {"specialists": {"5F": {"output": {"state": "LOCATION_QUALITY_PASS", "direction": "DOWN"}}}}),
        "E6": _engine("E6", {"specialists": {"6F": {"output": {"state": "DEVELOPING", "direction": "DOWN"}}}}),
        "E7": _engine("E7", {"specialists": {"7F": {"output": {"state": "CONFIRMATION_WAIT", "direction": "DOWN"}}}}),
    }

    result = _independent_setup_maturity(by, "SELL")

    assert result["explicit_e6_maturity"] is False
    assert result["mature"] is False
    assert result["state"] == "DEVELOPING"


def test_e9_accepts_mature_setup_only_when_e6_explicitly_says_mature():
    by = {
        "E3": _engine("E3", {"specialists": {"3F": {"output": {"state": "ALIGNED", "direction": "DOWN"}}}}),
        "E5": _engine("E5", {"specialists": {"5F": {"output": {"state": "LOCATION_QUALITY_PASS", "direction": "DOWN"}}}}),
        "E6": _engine("E6", {"specialists": {"6F": {"output": {"state": "MATURE", "direction": "DOWN"}}}}),
        "E7": _engine("E7", {"specialists": {"7F": {"output": {"state": "CONFIRMATION_WAIT", "direction": "DOWN"}}}}),
    }

    result = _independent_setup_maturity(by, "SELL")

    assert result["explicit_e6_maturity"] is True
    assert result["mature"] is True
    assert result["state"] == "MATURE"
