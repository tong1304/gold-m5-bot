import importlib
import sys


def test_scheduler_import_does_not_require_mt5_bridge(monkeypatch):
    monkeypatch.delenv("MT5_BRIDGE_URL", raising=False)
    sys.modules.pop("scheduler", None)
    importlib.import_module("scheduler")
