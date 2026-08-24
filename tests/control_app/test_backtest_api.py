from __future__ import annotations

import control_app.app as app_module
from control_app.backtest.models import BacktestResult


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

    def fake_run_backtest(symbol, start, end, **kwargs):
        return BacktestResult(
            run_id=kwargs["run_id"],
            symbol=symbol,
            start_time=start.isoformat(),
            end_time=end.isoformat(),
            engine_version="12.9-MTF-H1-M15-TREND-M5-BTC-GOLD-MULTI-TP",
            statistics={"total_trades": 0},
            trades=[],
        )

    monkeypatch.setattr("control_app.backtest.engine.run_backtest", fake_run_backtest)
    original_thread = app_module.threading.Thread

    def fake_thread(*args, **kwargs):
        class Immediate:
            def start(self_inner):
                kwargs["target"](*kwargs.get("args", ()))
        return Immediate()

    monkeypatch.setattr(app_module.threading, "Thread", fake_thread)
    response = app.test_client().post("/api/backtest", json={"symbol": "BTC", "start": "2026-08-01", "end": "2026-08-02"})
    assert response.status_code == 202
    run_id = response.get_json()["run_id"]
    stored = app.test_client().get(f"/api/backtest/{run_id}").get_json()
    assert stored["status"] == "completed"
    assert stored["result"]["metadata"]["live_orders_allowed"] is False
    monkeypatch.setattr(app_module.threading, "Thread", original_thread)
