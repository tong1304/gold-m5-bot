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
    assert json.loads((tmp_path / "state.json").read_text()) ["BTC"]["bars_waited"] == 1


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
