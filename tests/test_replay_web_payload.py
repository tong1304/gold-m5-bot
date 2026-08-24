from replay_web import _public_state


def test_replay_status_payload_does_not_return_all_replay_rows():
    state = {
        "running": False,
        "status": "completed",
        "result": {
            "status": "completed",
            "reports": [
                {"symbol": "BTC", "performance": {"wins": 3}, "rows": [{"candle_time": "x"}] * 5000}
            ],
        },
    }

    public = _public_state(state)

    assert public["result"]["reports"][0]["performance"]["wins"] == 3
    assert "rows" not in public["result"]["reports"][0]


def test_running_replay_exposes_progress_for_live_status_pages():
    state = {
        "running": True,
        "status": "running",
        "progress": {
            "symbol": "BTC",
            "completed": 120,
            "total": 406,
            "percent": 29.6,
            "trades": 5,
            "wins": 2,
            "losses": 3,
            "open": 0,
            "net_r": -0.8,
        },
        "result": None,
    }

    public = _public_state(state)

    assert public["progress"]["symbol"] == "BTC"
    assert public["progress"]["completed"] == 120
    assert public["progress"]["total"] == 406
    assert public["progress"]["percent"] == 29.6
