import importlib
import sys
import types

import pytest


def test_production_v2_fails_fast_without_lse_key(monkeypatch):
    monkeypatch.delenv("LSE_API_KEY", raising=False)
    sys.modules.pop("production_v2.app", None)
    with pytest.raises(RuntimeError, match="LSE_API_KEY is required"):
        importlib.import_module("production_v2.app")


def test_production_v2_starts_live_service_with_lse_key(monkeypatch):
    monkeypatch.setenv("LSE_API_KEY", "test-key")
    started = []
    fake_service = types.ModuleType("production_v2.service")
    fake_service.start_live_service = lambda: started.append(True)
    monkeypatch.setitem(sys.modules, "production_v2.service", fake_service)
    sys.modules.pop("production_v2.app", None)

    importlib.import_module("production_v2.app")

    assert started == [True]
