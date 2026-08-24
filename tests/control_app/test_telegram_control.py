from __future__ import annotations

from control_app.app import create_app


def test_telegram_toggle_and_persistence(tmp_path):
    path = tmp_path / "state.db"
    app = create_app({"DB_PATH": str(path), "TESTING": True})
    client = app.test_client()
    assert client.get("/api/telegram").get_json()["enabled"] is True
    response = client.post("/api/telegram/toggle", json={"enabled": False})
    assert response.status_code == 200
    assert response.get_json()["enabled"] is False

    app2 = create_app({"DB_PATH": str(path), "TESTING": True})
    assert app2.test_client().get("/api/telegram").get_json()["enabled"] is False


def test_telegram_toggle_rejects_non_boolean(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "state.db"), "TESTING": True})
    response = app.test_client().post("/api/telegram/toggle", json={"enabled": "false"})
    assert response.status_code == 400
