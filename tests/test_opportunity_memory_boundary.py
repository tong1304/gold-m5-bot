import importlib


def test_opportunity_memory_has_canonical_storage_implementation(tmp_path, monkeypatch):
    monkeypatch.setenv("OPPORTUNITY_MEMORY_PATH", str(tmp_path / "lifecycle.json"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("OPPORTUNITY_MEMORY_DATABASE_URL", raising=False)

    memory = importlib.import_module("production_v2.opportunity.memory")
    importlib.reload(memory)

    assert memory.backend() == "FILE"
    assert memory.load_all() == {}

    state = {"state": "WATCHING", "opportunity_id": "BUY|TREND"}
    memory.save("xauusd", state)
    assert memory.load("XAUUSD") == state

    memory.remove("XAUUSD")
    assert memory.load("XAUUSD") == {}


def test_legacy_memory_import_is_only_a_compatibility_facade():
    legacy = importlib.import_module("production_v2.opportunity_memory")
    canonical = importlib.import_module("production_v2.opportunity.memory")
    assert legacy.backend is canonical.backend
    assert legacy.load is canonical.load
    assert legacy.save is canonical.save
