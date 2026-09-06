import importlib


def test_opportunity_memory_round_trips_lifecycle_and_terminal_history(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("OPPORTUNITY_MEMORY_DATABASE_URL", raising=False)
    monkeypatch.delenv("PRODUCTION_V2_REQUIRE_PERSISTENT_MEMORY", raising=False)
    monkeypatch.setenv("OPPORTUNITY_MEMORY_PATH", str(tmp_path / "lifecycle.json"))

    import production_v2.opportunity_memory as memory
    memory = importlib.reload(memory)
    state = {
        "opportunities": {"SELL": {"opportunity_id": "SELL|WATCH|1", "state": "REPLACED"}},
        "leader": "NEUTRAL",
        "missed_opportunity_outcomes": [{
            "opportunity_id": "SELL|WATCH|1",
            "terminal_state": "REPLACED",
            "classification": "GOOD_WAIT",
        }],
    }
    memory.save("BTC", state)

    restarted = importlib.reload(memory)
    restored = restarted.load("BTC")
    assert restored["opportunities"]["SELL"]["opportunity_id"] == "SELL|WATCH|1"
    assert restored["missed_opportunity_outcomes"][0]["classification"] == "GOOD_WAIT"
