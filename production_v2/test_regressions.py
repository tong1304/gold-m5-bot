from production_v2.pipeline import _lifecycle_current
from production_v2.e3_brain import _sweep_reclaim


def test_lifecycle_does_not_invalidate_watch_from_e6_state_alone():
    results = {
        "E4": type("R", (), {"output": {}})(),
        "E6": type("R", (), {"output": {
            "state": "INVALIDATED",
            "lifecycle_state": "INVALIDATED",
            "direction": "SELL",
            "setup": "NO_SETUP",
            "invalidated": False,
        }})(),
    }
    current = _lifecycle_current(results, "NO_TRADE", False, "2026-09-05T03:05:00Z")
    assert current["invalidated"] is False


def test_sweep_reclaim_is_explicitly_non_reversal():
    bars = [
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
        {"open": 100.0, "high": 102.0, "low": 99.5, "close": 101.0},
        {"open": 101.0, "high": 101.2, "low": 100.0, "close": 100.4},
    ]
    highs = [{"index": 1, "price": 101.0, "confirmation_index": 1, "label": "LH"}]
    result = _sweep_reclaim(bars, highs, [], 1.0)
    assert result["event"] == "SWEEP_RECLAIM"
    assert result["structural_effect"] == "NONE"
    assert result["reversal_confirmed"] is False
