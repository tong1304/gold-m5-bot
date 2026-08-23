import json

import statistics_page_v10_3 as page


def test_build_exposes_detailed_entry_orders(monkeypatch):
    rows = [{
        "signal_id": "btc-001",
        "symbol": "BTC",
        "direction": "BUY",
        "candle_time": "2026-08-23T17:25:00+00:00",
        "created_at": "2026-08-23T17:26:00+00:00",
        "entry": 117000.5,
        "sl": 116800.5,
        "tp": 117400.5,
        "risk_reward": 2.0,
        "result": "OPEN",
        "r_multiple": None,
        "resolved_at": None,
        "telegram_sent": 1,
        "payload_json": json.dumps({
            "engine_version": "10.3-MULTI-M15-M5",
            "strategy": "MOMENTUM",
            "regime": "VOLATILITY_EXPANSION",
            "timeframe": "M5",
            "context_timeframe": "M15",
            "signal": "BUY",
            "trade_levels": {"entry": 117000.5, "sl": 116800.5, "tp": 117400.5, "risk_reward": 2.0},
            "reasons": ["SETUP_VALID"],
        }),
    }]
    monkeypatch.setattr(page, "_rows", lambda days=30, symbol=None: rows)

    result = page._build(30, "BTC")

    assert len(result["entries"]) == 1
    entry = result["entries"][0]
    assert entry["signal_id"] == "btc-001"
    assert entry["direction"] == "BUY"
    assert entry["strategy"] == "MOMENTUM"
    assert entry["regime"] == "VOLATILITY_EXPANSION"
    assert entry["entry"] == 117000.5
    assert entry["sl"] == 116800.5
    assert entry["tp"] == 117400.5
    assert entry["risk_reward"] == 2.0
    assert entry["result"] == "OPEN"
    assert entry["entry_time_thailand"]


def test_build_does_not_show_no_trade_as_entry(monkeypatch):
    rows = [{
        "signal_id": "btc-no-trade",
        "symbol": "BTC",
        "direction": "NO_TRADE",
        "candle_time": "2026-08-23T17:25:00+00:00",
        "created_at": "2026-08-23T17:26:00+00:00",
        "entry": None,
        "sl": None,
        "tp": None,
        "risk_reward": None,
        "result": "NO_TRADE",
        "r_multiple": None,
        "resolved_at": None,
        "telegram_sent": 0,
        "payload_json": json.dumps({"engine_version": "10.3-MULTI-M15-M5", "signal": "NO_TRADE"}),
    }]
    monkeypatch.setattr(page, "_rows", lambda days=30, symbol=None: rows)

    result = page._build(30, "BTC")

    assert result["entries"] == []
    assert result["overall"]["no_trade"] == 1
