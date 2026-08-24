from __future__ import annotations

import threading

from control_app.app import create_app


def test_create_app_does_not_start_live_services(tmp_path):
    before = {t.name for t in threading.enumerate()}
    app = create_app({"DB_PATH": str(tmp_path / "state.db"), "TESTING": True})
    after = {t.name for t in threading.enumerate()}
    assert before == after
    assert app.test_client().get("/api/health").status_code == 200
    assert "scheduler" not in " ".join(after).lower()


def test_health_exposes_only_telegram_control(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "state.db"), "TESTING": True})
    payload = app.test_client().get("/api/health").get_json()
    assert payload["telegram_enabled"] is True
    assert payload["live_services_started"] is False
