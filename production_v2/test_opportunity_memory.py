import json


def test_postgres_backend_selected_when_database_url_is_configured(monkeypatch):
    import production_v2.opportunity_memory as memory

    monkeypatch.setenv("OPPORTUNITY_MEMORY_DATABASE_URL", "postgresql://example")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert memory.backend() == "POSTGRES"


def test_file_backend_is_explicit_when_no_database_is_configured(monkeypatch, tmp_path):
    import production_v2.opportunity_memory as memory

    monkeypatch.delenv("OPPORTUNITY_MEMORY_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("OPPORTUNITY_MEMORY_PATH", str(tmp_path / "state.json"))
    assert memory.backend() == "FILE"

    memory.save("BTC", {"state": "WATCHING", "opportunity_id": "SELL|OPPORTUNITY_WATCH", "bars_waited": 1})
    assert memory.load("BTC")["opportunity_id"] == "SELL|OPPORTUNITY_WATCH"
    assert json.loads((tmp_path / "state.json").read_text())["BTC"]["bars_waited"] == 1


def test_production_requires_persistent_opportunity_memory(monkeypatch):
    import production_v2.opportunity_memory as memory

    monkeypatch.delenv("OPPORTUNITY_MEMORY_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PRODUCTION_V2_REQUIRE_PERSISTENT_MEMORY", "1")
    try:
        memory.require_persistent_backend()
    except RuntimeError as exc:
        assert "persistent opportunity memory" in str(exc).lower()
    else:
        raise AssertionError("FILE backend must not be accepted when persistence is required")


def test_pipeline_loads_and_saves_lifecycle_state(monkeypatch):
    import production_v2.opportunity_memory as memory
    import production_v2.pipeline as pipeline_module

    stored = {"state": "WATCHING", "opportunity_id": "BUY|OPPORTUNITY_WATCH", "bars_waited": 3}
    loaded = []
    saved = []

    monkeypatch.setattr(memory, "load", lambda symbol: loaded.append(symbol) or dict(stored))
    monkeypatch.setattr(memory, "save", lambda symbol, state: saved.append((symbol, dict(state))))

    monkeypatch.setattr(pipeline_module, "build_shared_market_picture", lambda snapshot: {})
    monkeypatch.setattr(pipeline_module, "analyze_e1", lambda bars: {"finding": "MARKET_STATE=TRANSITION"})
    monkeypatch.setattr(pipeline_module, "analyze_e2", lambda snapshot: {"finding": "NEUTRAL"})
    monkeypatch.setattr(pipeline_module, "analyze_e3", lambda bars: {"finding": "STRUCTURE_FORMING"})
    monkeypatch.setattr(pipeline_module, "analyze_e4", lambda snapshot, results: {})
    monkeypatch.setattr(pipeline_module, "analyze_e5", lambda snapshot, results: {})
    monkeypatch.setattr(pipeline_module, "analyze_e6", lambda snapshot, results: {"finding": "BUY opportunity watch", "candidate_type": "OPPORTUNITY_CANDIDATE", "direction": "BUY", "trade_ready": False, "e6_thesis_proven": False, "missing_proof": ["E7_CONFIRMATION"]})
    monkeypatch.setattr(pipeline_module, "analyze_e7", lambda snapshot, results: {"finding": "WATCH", "confirmation_state": "PENDING"})
    monkeypatch.setattr(pipeline_module, "analyze_e8", lambda snapshot, results: {"finding": "NOT_APPLICABLE"})
    monkeypatch.setattr(pipeline_module, "analyze_e9", lambda snapshot, results: {"decision": "NO_TRADE", "trade_ready": False, "gate_passed": False})
    monkeypatch.setattr(pipeline_module, "audit_engines", lambda results: {})
    monkeypatch.setattr(pipeline_module, "enforce_final_authority", lambda e9, results: e9)
    monkeypatch.setattr(pipeline_module, "audit_all", lambda results: None)
    monkeypatch.setattr(pipeline_module, "audit_shared_market_picture_contract", lambda results: {"passed": True})
    monkeypatch.setattr(pipeline_module, "build_conflict_ledger", lambda results: {})

    result = pipeline_module.ProductionPipeline().run({"symbol": "BTC", "bars": [], "candle": "2026-09-06T06:55:00Z"})

    assert loaded == ["BTC"]
    assert saved and saved[-1][0] == "BTC"
    assert saved[-1][1]["state"] in {"WATCHING", "WAITING", "READY", "IDLE", "INVALIDATED", "EXPIRED", "REPLACED"}
    assert result.decision == "NO_TRADE"
