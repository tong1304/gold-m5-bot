import importlib

def test_v11_engine_has_no_legacy_engine_dependency():
    module=importlib.import_module("v11.engine")
    assert module.ENGINE_VERSION=="11.1-HARDENED"
    assert not any(name.startswith("engine_v9") or name.startswith("engine_v5") for name in module.__dict__)
