from __future__ import annotations

import control_app.app as app_module


def test_backtest_rejects_invalid_symbol(tmp_path):
    app = app_module.create_app({"DB_PATH": str(tmp_path / "state.db"), "TESTING": True})
    response = app.test_client().post("/api/backtest", json={"symbol": "ETH", "start": "2026-08-01", "end": "2026-08-02"})
    assert response.status_code == 400


def test_backtest_rejects_invalid_date_range(tmp_path):
    app = app_module.create_app({"DB_PATH": str(tmp_path / "state.db"), "TESTING": True})
    response = app.test_client().post("/api/backtest", json={"symbol": "BTC", "start": "2026-08-02", "end": "2026-08-01"})
    assert response.status_code == 400


def test_backtest_starts_without_telegram_call(tmp_path, monkeypatch):
    app = app_module.create_app({"DB_PATH": str(tmp_path / "state.db"), "TESTING": True})
    calls = []
    monkeypatch.setattr(app_module, "threading", app_module.threading)
    original_worker = app_module.threading.Thread

    def fake_thread(*args, **kwargs):
        class Immediate:
            def start(self_inner):
                target = kwargs.get("target")
                target_args = kwargs.get("args", ())
                if target:
                    target(*target_args)
        return Immediate()

    monkeypatch.setattr(app_module.threading, "Thread", fake_thread)
    response = app.test_client().post("/api/backtest", json={"symbol": "BTC", "start": "2026-08-01", "end": "2026-08-02"})
    assert response.status_code == 202
    monkeypatch.setattr(app_module.threading, "Thread", original_worker)
