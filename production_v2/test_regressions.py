from production_v2.pipeline import _lifecycle_current
from production_v2.opportunity_memory import load, save


def _result(output):
    return type("R", (), {"output": output})()


def test_absent_e6_does_not_invalidate_pending_watch():
    results = {
        "E3": _result({"invalidation": {"invalidated": False}}),
        "E4": _result({}),
        "E6": _result({
            "state": "NO_SETUP",
            "lifecycle_state": "NO_SETUP",
            "direction": "NEUTRAL",
            "setup": "NO_SETUP",
            "invalidated": False,
            "upstream_evidence_lost": False,
            "causal_evidence_lost": False,
        }),
    }
    current = _lifecycle_current(results, "NO_TRADE", False, "2026-09-05T03:05:00Z")
    assert current["invalidated"] is False


def test_explicit_e6_invalidation_is_preserved():
    results = {
        "E3": _result({"invalidation": {"invalidated": False}}),
        "E4": _result({}),
        "E6": _result({
            "state": "INVALIDATED",
            "lifecycle_state": "INVALIDATED",
            "direction": "NEUTRAL",
            "setup": "NO_SETUP",
            "invalidated": True,
            "invalidation_reason": "E3_STRUCTURE_INVALIDATED",
            "upstream_evidence_lost": True,
            "causal_evidence_lost": True,
        }),
    }
    current = _lifecycle_current(results, "NO_TRADE", False, "2026-09-05T03:05:00Z")
    assert current["invalidated"] is True


def test_opportunity_memory_round_trip(tmp_path, monkeypatch):
    path = tmp_path / "opportunity.json"
    monkeypatch.setenv("OPPORTUNITY_MEMORY_PATH", str(path))
    state = {
        "state": "WATCHING",
        "direction": "BUY",
        "opportunity_id": "BTC-20260905-0750",
        "bars_waited": 2,
    }
    save("BTC", state)
    assert load("BTC") == state
