import importlib


def test_production_v2_requires_live_data_configuration(monkeypatch):
    monkeypatch.delenv("LSE_API_KEY", raising=False)
    import production_v2.app as app_module
    app_module = importlib.reload(app_module)
    assert app_module.app is not None
    assert app_module.app.config["PRODUCTION_V2_LIVE_REQUIRED"] is True


def test_production_v2_starts_live_service_when_lse_key_exists(monkeypatch):
    monkeypatch.setenv("LSE_API_KEY", "test-key")
    started = []

    import production_v2.app as app_module
    monkeypatch.setattr(app_module, "start_live_service", lambda: started.append(True), raising=False)
    importlib.reload(app_module)
    assert started == [True]
